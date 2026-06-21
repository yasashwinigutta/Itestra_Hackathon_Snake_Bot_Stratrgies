import heapq
from collections import deque, defaultdict
from typing import Tuple, List, Set, Dict, Any, Optional

# Strategy: Risk-Aware Star-Control Apple Hunter

Coord = Tuple[int, int]

# Weights and penalties tuned to the spec
WEIGHTS = {
    "good_apple": 140.0,
    "bad_apple_penalty": 220.0,
    "safe_star": 600.0,
    "boosted_kill": 1200.0,
    "open_space": 1.0,
    "enemy_head_1": 300.0,
    "enemy_head_2": 90.0,
    "enemy_head_3": 30.0,
    "dead_end": 450.0,
}


def wrap_position(pos: Coord, size: Tuple[int, int]) -> Coord:
    w, h = size
    return (pos[0] % w, pos[1] % h)


def wrapped_neighbors(pos: Coord, size: Tuple[int, int]) -> List[Coord]:
    w, h = size
    x, y = pos
    return [((x + 1) % w, y), ((x - 1) % w, y), (x, (y + 1) % h), (x, (y - 1) % h)]


def toroidal_distance(a: Coord, b: Coord, size: Tuple[int, int]) -> int:
    w, h = size
    dx = min(abs(a[0] - b[0]), w - abs(a[0] - b[0]))
    dy = min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))
    return dx + dy


def get_head(snake: Any) -> Optional[Coord]:
    try:
        return tuple(snake.body[0])
    except Exception:
        return None


def get_body(snake: Any) -> List[Coord]:
    try:
        return [tuple(p) for p in snake.body]
    except Exception:
        return []


def is_good_apple(item: Any) -> bool:
    return getattr(item, "kind", "") == "Apple"


def is_bad_apple(item: Any) -> bool:
    return getattr(item, "kind", "") == "BadApple"


def get_star(field: Any) -> Optional[Coord]:
    for it in getattr(field, "items", []) or []:
        if getattr(it, "kind", "") in ("Star", "STAR", "star"):
            return tuple(it.position)
    return None


def is_boosted(snake: Any) -> bool:
    if not snake:
        return False
    for e in getattr(snake, "active_effects", []) or []:
        if getattr(e, "effect", "").lower() in ("star_boost", "boost", "star") and getattr(e, "remaining_ticks", 0) > 0:
            return True
    inv = getattr(snake, "inventory", []) or []
    if any(str(x).lower().startswith("star") for x in inv):
        return True
    return False


def enemy_danger_zones(field: Any, team_name: str, depth: int = 3) -> Dict[Coord, int]:
    size = getattr(field, "size")
    dangers: Dict[Coord, int] = defaultdict(int)

    step_weights = {1: WEIGHTS["enemy_head_1"], 2: WEIGHTS["enemy_head_2"], 3: WEIGHTS["enemy_head_3"]}

    for name, s in getattr(field, "snakes", {}).items():
        if name == team_name:
            continue
        head = get_head(s)
        if head is None:
            continue
        boosted = is_boosted(s)
        mul = 6 if boosted else 1

        # 1..depth neighbor expansions
        frontier = {head}
        visited = set(frontier)
        for d in range(1, depth + 1):
            weight = step_weights.get(d, 10) * mul
            next_frontier = set()
            for cell in frontier:
                for nb in wrapped_neighbors(cell, size):
                    if nb in visited:
                        continue
                    dangers[nb] += int(weight)
                    visited.add(nb)
                    next_frontier.add(nb)
            frontier = next_frontier

        # mark body strongly
        for seg in get_body(s):
            dangers[seg] += 300 * mul

    return dict(dangers)


def boosted_enemy_zones(field: Any, team_name: str) -> Set[Coord]:
    zones = set()
    size = getattr(field, "size")
    for name, s in getattr(field, "snakes", {}).items():
        if name == team_name:
            continue
        if is_boosted(s):
            head = get_head(s)
            if not head:
                continue
            # predict 3-step zone
            z = {head}
            for _ in range(3):
                z = {nb for c in z for nb in wrapped_neighbors(c, size)} | z
            zones |= z
            # include body
            zones |= set(get_body(s))
    return zones


def is_cell_safe(pos: Coord, field: Any, team_name: str, powered: bool = False) -> bool:
    pos = wrap_position(pos, getattr(field, "size"))
    my_snake = field.snakes.get(team_name)
    # own body collision is illegal
    if my_snake and pos in get_body(my_snake):
        return False

    # enemy body collision when not boosted is illegal
    for name, s in field.snakes.items():
        if name == team_name:
            continue
        if not powered and pos in get_body(s):
            return False

    dangers = enemy_danger_zones(field, team_name, depth=3)
    if dangers.get(pos, 0) >= WEIGHTS["enemy_head_1"]:
        # immediate high danger
        return False

    boosted_z = boosted_enemy_zones(field, team_name)
    if pos in boosted_z and not powered:
        return False

    # simple trap detection: reachable area small
    area = reachable_area_size(pos, field, team_name, limit=50)
    if area <= 2:
        return False

    return True


def path_to_target(start: Coord, target: Coord, field: Any, team_name: str, allow_bad_apples: bool = True) -> Optional[List[Coord]]:
    w, h = field.size
    start = wrap_position(start, field.size)
    target = wrap_position(target, field.size)

    obstacles = set()
    for name, s in field.snakes.items():
        # treat enemy bodies as obstacles for path planning when not boosted
        body = get_body(s)
        obstacles.update(body)

    bad_apples = {tuple(it.position) for it in getattr(field, "items", []) if is_bad_apple(it)}

    def heuristic(a, b):
        return toroidal_distance(a, b, field.size)

    open_set = [(heuristic(start, target), 0, start)]
    came_from: Dict[Coord, Coord] = {}
    gscore = {start: 0}

    while open_set:
        _, g, cur = heapq.heappop(open_set)
        if cur == target:
            path = [cur]
            while path[-1] != start:
                path.append(came_from[path[-1]])
            path.reverse()
            return path

        for nb in wrapped_neighbors(cur, field.size):
            if nb in obstacles and nb != target:
                continue
            if not allow_bad_apples and nb in bad_apples and nb != target:
                continue

            tentative = g + 1
            if nb not in gscore or tentative < gscore[nb]:
                gscore[nb] = tentative
                came_from[nb] = cur
                heapq.heappush(open_set, (tentative + heuristic(nb, target), tentative, nb))

    return None


def move_from_step(step: Coord, head: Coord, size: Tuple[int, int]) -> Optional[str]:
    w, h = size
    dx = (step[0] - head[0]) % w
    dy = (step[1] - head[1]) % h
    if dx == 1:
        return "EAST"
    if dx == w - 1:
        return "WEST"
    if dy == 1:
        return "SOUTH"
    if dy == h - 1:
        return "NORTH"
    return None


def reachable_area_size(start: Coord, field: Any, team_name: str, limit: int = 1000) -> int:
    seen = set()
    q = deque([start])
    size = field.size
    count = 0
    while q and count < limit:
        cur = q.popleft()
        if cur in seen:
            continue
        if not is_cell_safe(cur, field, team_name, powered=is_boosted(field.snakes.get(team_name))):
            continue
        seen.add(cur)
        count += 1
        for nb in wrapped_neighbors(cur, size):
            if nb not in seen:
                q.append(nb)
    return count


def score_move(direction: str, field: Any, team_name: str, current_direction: str) -> float:
    me = field.snakes.get(team_name)
    if not me or not me.body:
        return -1e9
    head = get_head(me)
    size = field.size
    w, h = size

    # next pos
    if direction == "NORTH":
        pos = (head[0], (head[1] - 1) % h)
    elif direction == "SOUTH":
        pos = (head[0], (head[1] + 1) % h)
    elif direction == "EAST":
        pos = ((head[0] + 1) % w, head[1])
    else:
        pos = ((head[0] - 1) % w, head[1])

    # illegal moves
    if not is_cell_safe(pos, field, team_name, powered=is_boosted(me)):
        return -1e9

    score = 0.0

    # GOOD APPLES: prefer close, safe, uncontested
    apples = [it for it in field.items if is_good_apple(it)]
    for a in apples:
        a_pos = tuple(a.position)
        d = toroidal_distance(pos, a_pos, size)
        # contested check: nearest enemy distance to apple
        enemy_nearest = min((toroidal_distance(get_head(s), a_pos, size) for n, s in field.snakes.items() if n != team_name and get_head(s) is not None), default=999)
        contested = enemy_nearest < toroidal_distance(head, a_pos, size)
        if contested:
            bonus = WEIGHTS["good_apple"] / (d + 3) * 0.3
        else:
            bonus = WEIGHTS["good_apple"] / (d + 1)
        score += bonus

    # BAD APPLES: strong penalty
    bads = [it for it in field.items if is_bad_apple(it)]
    for b in bads:
        d = toroidal_distance(pos, tuple(b.position), size)
        score -= WEIGHTS["bad_apple_penalty"] / (d + 1)

    # STAR: safe chase if strictly closer
    star = get_star(field)
    if star:
        my_dist = toroidal_distance(head, star, size)
        enemy_dists = [toroidal_distance(get_head(s), star, size) for n, s in field.snakes.items() if n != team_name and get_head(s) is not None]
        nearest_enemy = min(enemy_dists) if enemy_dists else 999
        if my_dist < nearest_enemy:
            path = path_to_target(head, star, field, team_name, allow_bad_apples=True)
            if path and len(path) >= 2 and pos == path[1]:
                # prefer few bad apples along path
                bads_on_path = sum(1 for p in path if p in {tuple(x.position) for x in getattr(field, "items", []) if is_bad_apple(x)})
                score += WEIGHTS["safe_star"] - bads_on_path * 120
        else:
            # contested: penalize moves toward star
            if toroidal_distance(pos, star, size) < toroidal_distance(head, star, size):
                score -= 120.0

    # enemy danger contributions (from predicted zones)
    dangers = enemy_danger_zones(field, team_name, depth=3)
    score -= dangers.get(pos, 0) * 0.9

    # proximity to enemy heads (explicit penalties)
    for n, s in field.snakes.items():
        if n == team_name:
            continue
        ehead = get_head(s)
        if not ehead:
            continue
        d = toroidal_distance(pos, ehead, size)
        if d == 0 and not is_boosted(me):
            return -1e9
        if d == 1:
            score -= WEIGHTS["enemy_head_1"]
        elif d == 2:
            score -= WEIGHTS["enemy_head_2"]
        elif d == 3:
            score -= WEIGHTS["enemy_head_3"]

    # boosted enemy strict avoidance
    if any(is_boosted(s) for n, s in field.snakes.items() if n != team_name):
        bz = boosted_enemy_zones(field, team_name)
        if pos in bz and not is_boosted(me):
            return -1e9

    # boosted kill scoring when we are powered
    if is_boosted(me):
        # reward being within kill range of enemy heads/bodies
        for n, s in field.snakes.items():
            if n == team_name:
                continue
            ehead = get_head(s)
            if not ehead:
                continue
            d = toroidal_distance(pos, ehead, size)
            if d == 0:
                score += WEIGHTS["boosted_kill"] * 1.2
            elif d == 1:
                score += WEIGHTS["boosted_kill"]
            # bonus for hitting longer snakes
            score += len(get_body(s)) * 2.0

    # open space
    open_space = reachable_area_size(pos, field, team_name, limit=100)
    score += WEIGHTS["open_space"] * open_space

    # dead end penalty
    if open_space <= 3:
        score -= WEIGHTS["dead_end"]

    # small continue-straight bias
    if direction == current_direction:
        score += 5.0

    return score


def choose_direction(field: Any, team_name: str, current_direction: str) -> str:
    me = field.snakes.get(team_name)
    if not me or not me.body:
        return current_direction
    head = get_head(me)
    w, h = field.size

    opposite = {"NORTH": "SOUTH", "SOUTH": "NORTH", "EAST": "WEST", "WEST": "EAST"}
    forbidden = opposite.get(current_direction)

    moves = {
        "NORTH": (head[0], (head[1] - 1) % h),
        "SOUTH": (head[0], (head[1] + 1) % h),
        "EAST": ((head[0] + 1) % w, head[1]),
        "WEST": ((head[0] - 1) % w, head[1]),
    }

    candidates = [d for d in moves.keys() if d != forbidden]

    # priority 1: immediate boosted enemy avoidance
    for name, s in field.snakes.items():
        if name == team_name:
            continue
        if is_boosted(s):
            # maximize distance from boosted head
            best = max(candidates, key=lambda d: toroidal_distance(moves[d], get_head(s), field.size))
            return best

    # priority 2: if we are boosted, seek safe kills
    if is_boosted(me):
        kill_options = []
        for d in candidates:
            pos = moves[d]
            for name, s in field.snakes.items():
                if name == team_name:
                    continue
                if toroidal_distance(pos, get_head(s), field.size) <= 2:
                    # estimate safety after move
                    area = reachable_area_size(pos, field, team_name, limit=60)
                    kill_options.append((d, area, len(get_body(s)), toroidal_distance(pos, get_head(s), field.size)))
        if kill_options:
            # prefer head proximity, then longer snake, then safety
            kill_options.sort(key=lambda x: (x[3], -x[2], -x[1]))
            return kill_options[0][0]

    # priority 3: star handling
    star = get_star(field)
    if star:
        my_dist = toroidal_distance(head, star, field.size)
        enemy_dists = [toroidal_distance(get_head(s), star, field.size) for n, s in field.snakes.items() if n != team_name and get_head(s) is not None]
        nearest_enemy = min(enemy_dists) if enemy_dists else 999
        if my_dist < nearest_enemy:
            path = path_to_target(head, star, field, team_name, allow_bad_apples=True)
            if path and len(path) >= 2:
                # ensure path safety for early segments
                safe = all(is_cell_safe(p, field, team_name, powered=is_boosted(me)) for p in path[1: min(len(path), 6)])
                if safe:
                    step = path[1]
                    move = move_from_step(step, head, field.size)
                    if move and move in candidates:
                        return move
        else:
            # contested -> bias away from star
            candidates.sort(key=lambda d: toroidal_distance(moves[d], star, field.size), reverse=True)

    # priority 4: prefer safe nearby good apples
    apples = [it for it in field.items if is_good_apple(it)]
    for d in candidates:
        pos = moves[d]
        for a in apples:
            path = path_to_target(pos, tuple(a.position), field, team_name, allow_bad_apples=False)
            if path:
                # ensure not contested
                enemy_nearest = min((toroidal_distance(get_head(s), tuple(a.position), field.size) for n, s in field.snakes.items() if n != team_name and get_head(s) is not None), default=999)
                if toroidal_distance(head, tuple(a.position), field.size) < enemy_nearest:
                    return d

    # priority 5+: scoring fallback
    best = None
    best_score = -1e9
    for d in candidates:
        sc = score_move(d, field, team_name, current_direction)
        if sc > best_score:
            best_score = sc
            best = d

    # fallback survival: continue straight if safe
    if best is None or best_score < 0:
        straight = current_direction
        if straight != forbidden and straight in candidates and is_cell_safe(moves[straight], field, team_name, powered=is_boosted(me)):
            return straight
        # choose candidate with largest open space
        best_area = -1
        best_move = candidates[0]
        for d in candidates:
            area = reachable_area_size(moves[d], field, team_name, limit=200)
            if area > best_area:
                best_area = area
                best_move = d
        return best_move

    return best


def choose_next_move(my_head: Coord, obstacles: Set[Coord], snakes: List[Dict[str, Any]], field_size: Tuple[int, int], items: List[Any], current_direction: str) -> str:
    # compatibility wrapper used by main.py
    class _Snake:
        def __init__(self, body, alive=True):
            self.body = body
            self.alive = alive
            self.inventory = []
            self.active_effects = []

    class _Field:
        def __init__(self, size, snakes, items):
            self.size = size
            self.snakes = snakes
            self.items = items

    snakes_dict = {}
    for s in snakes:
        name = s.get("name")
        snakes_dict[name] = _Snake(s.get("body", []), True)

    # ensure our own head entry
    if "me" not in snakes_dict:
        snakes_dict["me"] = _Snake([my_head])

    fake_field = _Field(field_size, snakes_dict, items)
    # choose team name heuristically
    team_name = None
    for n, s in snakes_dict.items():
        if s.body and tuple(s.body[0]) == tuple(my_head):
            team_name = n
            break
    if not team_name:
        team_name = list(snakes_dict.keys())[0]

    return choose_direction(fake_field, team_name, current_direction)
