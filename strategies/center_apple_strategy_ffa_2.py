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
    # legacy wrapper kept for compatibility — prefer using enemy_head_danger_zones
    return enemy_head_danger_zones(field, team_name, depth)


def get_direction_from_body(snake: Any, default: Coord = (0, -1)) -> Coord:
    """Infer heading vector (dx,dy) from snake body: head - neck (toroidal-aware)."""
    head = get_head(snake)
    body = get_body(snake)
    if not head or len(body) < 2:
        return default
    neck = body[1]
    w, h = getattr(snake, "_field_size", (None, None)) if hasattr(snake, "_field_size") else (None, None)
    # if no size, fall back to direct delta
    dx = head[0] - neck[0]
    dy = head[1] - neck[1]
    # normalize to -1/0/1
    if dx != 0:
        dx = 1 if dx > 0 else -1
    if dy != 0:
        dy = 1 if dy > 0 else -1
    return (dx, dy)


def get_possible_head_moves(head: Coord, neck: Optional[Coord], size: Tuple[int, int]) -> List[Coord]:
    """Return legal next head positions excluding reversing into neck."""
    w, h = size
    candidates = [((head[0] + 1) % w, head[1]), ((head[0] - 1) % w, head[1]), (head[0], (head[1] + 1) % h), (head[0], (head[1] - 1) % h)]
    if neck is None:
        return candidates
    # exclude neck (reverse)
    filtered = [c for c in candidates if c != neck]
    return filtered


def enemy_head_danger_zones(field: Any, team_name: str, depth: int = 3) -> Dict[Coord, int]:
    """Predict enemy head reachable cells for 1..depth and assign danger weights.
    Returns dict cell->weight and also stores immediate_next_heads in _meta return via attribute on field for reuse.
    """
    size = getattr(field, "size")
    w, h = size
    dangers: Dict[Coord, int] = defaultdict(int)
    immediate_next_heads: Set[Coord] = set()

    weights = {1: WEIGHTS["enemy_head_1"], 2: WEIGHTS["enemy_head_2"], 3: WEIGHTS["enemy_head_3"]}

    for name, s in getattr(field, "snakes", {}).items():
        if name == team_name:
            continue
        head = get_head(s)
        if not head:
            continue
        body = get_body(s)
        neck = body[1] if len(body) >= 2 else None

        # depth 1: possible immediate head moves
        step1 = get_possible_head_moves(head, neck, size)
        for c in step1:
            dangers[c] += weights[1]
            immediate_next_heads.add(c)

        # depth expansions
        frontier = set(step1)
        visited = set(frontier) | {head}
        for d in range(2, depth + 1):
            next_frontier = set()
            for cell in frontier:
                # for enemy, their next moves cannot reverse into what was their head previous step here; approximate by allowing all neighbors
                for nb in wrapped_neighbors(cell, size):
                    if nb in visited:
                        continue
                    dangers[nb] += weights.get(d, 10)
                    next_frontier.add(nb)
                    visited.add(nb)
            frontier = next_frontier

        # Optionally de-emphasize body marking — keep small penalty to avoid stepping onto body
        for seg in body:
            dangers[seg] += 40

    # attach immediate set for caller convenience
    setattr(field, "_immediate_enemy_heads", immediate_next_heads)
    return dict(dangers)


def danger_score(pos: Coord, danger_zones: Dict[Coord, int]) -> int:
    return danger_zones.get(pos, 0)


def is_collision_cell(pos: Coord, field: Any, team_name: str) -> bool:
    """True if moving into pos would be an immediate illegal collision (own body or enemy body when not boosted)."""
    my_snake = field.snakes.get(team_name)
    if my_snake and pos in get_body(my_snake):
        return True
    for name, s in field.snakes.items():
        if name == team_name:
            continue
        if pos in get_body(s) and not is_boosted(my_snake):
            return True
    return False


def is_risky_cell(pos: Coord, field: Any, team_name: str, danger_zones: Dict[Coord, int]) -> bool:
    """Risk criteria: adjacent to enemy head, in immediate next-head set, or high danger weight."""
    # immediate predicted moves
    immediate = getattr(field, "_immediate_enemy_heads", set())
    if pos in immediate:
        return True
    # high danger weight
    if danger_score(pos, danger_zones) >= WEIGHTS["enemy_head_1"]:
        return True
    # adjacent to enemy head positions
    for name, s in field.snakes.items():
        if name == team_name:
            continue
        ehead = get_head(s)
        if not ehead:
            continue
        if toroidal_distance(pos, ehead, field.size) == 1:
            return True
    return False


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

    # compute enemy head danger zones once
    danger_zones = enemy_head_danger_zones(field, team_name, depth=3)
    immediate_heads = getattr(field, "_immediate_enemy_heads", set())

    # helper: count enemy heads adjacent to pos
    def adjacent_enemy_heads(pos: Coord) -> int:
        cnt = 0
        for n, s in field.snakes.items():
            if n == team_name:
                continue
            ehead = get_head(s)
            if not ehead:
                continue
            if toroidal_distance(pos, ehead, field.size) == 1:
                cnt += 1
        return cnt

    # eliminate illegal collision moves immediately
    legal = [d for d in candidates if not is_collision_cell(moves[d], field, team_name)]

    # prefer moves that are not immediate head targets
    safe_by_head = [d for d in legal if moves[d] not in immediate_heads and not is_risky_cell(moves[d], field, team_name, danger_zones)]

    # if straight is safe and not head-dangerous, keep going
    if current_direction in safe_by_head:
        return current_direction

    # if any safe_by_head moves exist, pick highest scoring among them
    options = safe_by_head if safe_by_head else legal

    # if no legal moves (rare), allow candidates and will be handled by score
    if not options:
        options = candidates

    # avoid moves that equal any immediate enemy next head if alternatives exist
    non_crash_options = [d for d in options if moves[d] not in immediate_heads]
    if non_crash_options:
        options = non_crash_options

    # filter out positions adjacent to multiple enemy heads strongly
    filtered = []
    for d in options:
        pos = moves[d]
        if adjacent_enemy_heads(pos) >= 2:
            continue
        filtered.append(d)
    if filtered:
        options = filtered

    # if boosted and opportunistic, allow slight risk but prefer safe
    if is_boosted(me):
        # choose option maximizing opportunistic opportunities (handled in score_move)
        pass

    # scoring selection among remaining options
    best = None
    best_score = -1e9
    for d in options:
        sc = score_move(d, field, team_name, current_direction)
        # penalize being in immediate head set heavily
        if moves[d] in immediate_heads and len(options) > 1:
            sc -= 1e6
        # penalize if risky
        if is_risky_cell(moves[d], field, team_name, danger_zones):
            sc -= WEIGHTS["enemy_head_2"]
        if sc > best_score:
            best_score = sc
            best = d

    # fallback: if best is None, try straight or any legal
    if best is None:
        if current_direction in legal:
            return current_direction
        if legal:
            return legal[0]
        return candidates[0]

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
