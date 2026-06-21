import heapq


# ========== CONFIGURATION ==========
STAR_REWARD = 650
CONTESTED_STAR_PENALTY = 220
POWERED_KILL_REWARD = 260
BAD_APPLE_PENALTY = 75
ENEMY_DANGER_PENALTY = 140
OPEN_SPACE_WEIGHT = 3.2
STAR_RACE_MARGIN = 0
BOOST_END_SAFETY_MARGIN = 3


# ========== TORUS DIST ==========
def torus_dist(a, b, w, h):
    dx = min(abs(a[0] - b[0]), w - abs(a[0] - b[0]))
    dy = min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))
    return dx + dy


# ========== MANHATTAN ==========
def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ========== NEIGHBORS ==========
def neighbors(node, w, h):
    x, y = node
    return [
        ((x + 1) % w, y),
        ((x - 1) % w, y),
        (x, (y + 1) % h),
        (x, (y - 1) % h),
    ]


# ========== ESCAPE SCORE ==========
def escape_score(pos, obstacles, w, h):
    x, y = pos
    return sum(
        ((x + dx) % w, (y + dy) % h) not in obstacles
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]
    )


# ========== ITEM HELPERS ==========
def item_position(item):
    if hasattr(item, "position"):
        return tuple(item.position)

    if isinstance(item, dict):
        pos = item.get("position")
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            return (int(pos[0]), int(pos[1]))

    if isinstance(item, (list, tuple)) and len(item) >= 1:
        pos = item[0]
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            return (int(pos[0]), int(pos[1]))

    return None


def item_kind(item):
    if hasattr(item, "kind"):
        return item.kind
    if isinstance(item, dict):
        return item.get("kind")
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        return item[1]
    return None


def item_value(item):
    value = getattr(item, "value", None)
    if isinstance(value, (int, float)):
        return value

    kind = item_kind(item)
    if kind == "Apple":
        return 1
    if kind == "BadApple":
        return -1
    if isinstance(kind, str) and "bad" in kind.lower():
        return -1
    if isinstance(kind, str) and "apple" in kind.lower():
        return 1

    return 0


def item_is_star(item):
    kind = item_kind(item)
    if isinstance(kind, str) and kind.lower() == "star":
        return True
    if isinstance(kind, str) and "star" in kind.lower():
        return True
    return False


def classify_items(items):
    good_apples = []
    bad_apples = []
    stars = []

    for item in items:
        pos = item_position(item)
        if pos is None:
            continue

        if item_is_star(item):
            stars.append({"pos": pos, "value": STAR_REWARD})
            continue

        value = item_value(item)
        if value > 0:
            good_apples.append({"pos": pos, "value": value})
        else:
            bad_apples.append({"pos": pos, "value": value})

    return good_apples, bad_apples, stars


def snake_has_power(snake):
    if not snake:
        return False

    for effect in snake.get("active_effects", []):
        if isinstance(effect, dict):
            name = str(effect.get("effect", "")).lower()
        elif isinstance(effect, str):
            name = effect.lower()
        else:
            name = ""

        if "star" in name or "powered" in name or "boost" in name:
            return True

    return False


def power_remaining(effects):
    best = 0
    for effect in effects or []:
        if isinstance(effect, dict) and "remaining_ticks" in effect:
            try:
                best = max(best, int(effect.get("remaining_ticks", 0)))
            except Exception:
                pass
    return best


# ========== SAFE CELL HELPERS ==========
def is_safe(pos, obstacles, w, h):
    if pos in obstacles:
        return False
    if escape_score(pos, obstacles, w, h) <= 1:
        return False
    return True


def is_adjacent_to_bad(pos, bad_positions, w, h):
    return any(neighbor in bad_positions for neighbor in neighbors(pos, w, h))


# ========== PATH SEARCH ==========
def astar(start, goal, obstacles, w, h):
    pq = [(0, start)]
    came = {}
    cost = {start: 0}

    while pq:
        _, cur = heapq.heappop(pq)
        if cur == goal:
            break

        for nxt in neighbors(cur, w, h):
            if nxt in obstacles:
                continue

            nc = cost[cur] + 1
            if nxt not in cost or nc < cost[nxt]:
                cost[nxt] = nc
                came[nxt] = cur
                heapq.heappush(pq, (nc + torus_dist(nxt, goal, w, h), nxt))

    if goal not in came and goal != start:
        return None, None, []

    path = [goal]
    cur = goal
    while cur != start:
        cur = came[cur]
        path.append(cur)
    path.reverse()

    first_step = path[1] if len(path) > 1 else path[0]
    return first_step, len(path) - 1, path


def shortest_star_path(start, goal, blocked, bad_positions, danger_zones, w, h):
    pq = [(0, 0, 0, start)]
    best = {start: (0, 0, 0)}
    prev = {start: None}

    while pq:
        dist_so_far, bad_so_far, danger_so_far, pos = heapq.heappop(pq)
        if best.get(pos, (1e9, 1e9, 1e9)) < (dist_so_far, bad_so_far, danger_so_far):
            continue

        if pos == goal:
            path = []
            cur = pos
            while cur is not None:
                path.append(cur)
                cur = prev[cur]
            path.reverse()
            first_step = path[1] if len(path) > 1 else path[0]
            return dist_so_far, bad_so_far, danger_so_far, first_step, path

        for nxt in neighbors(pos, w, h):
            if nxt in blocked:
                continue

            next_bad = bad_so_far + (1 if nxt in bad_positions else 0)
            next_danger = danger_so_far + (1 if nxt in danger_zones else 0)
            state = (dist_so_far + 1, next_bad, next_danger)

            if nxt not in best or state < best[nxt]:
                best[nxt] = state
                prev[nxt] = pos
                heapq.heappush(pq, (state[0], state[1], state[2], nxt))

    return None, None, None, None, None


# ========== ENEMY PREDICTION ==========
def predicted_enemy_zones(snakes, obstacles, w, h, my_head=None, steps=3):
    danger = set()

    for s in snakes:
        head = s["head"]
        if my_head is not None and head == my_head:
            continue

        body = set(s.get("body", []))
        forbidden = None
        if len(s.get("body", [])) >= 2:
            forbidden = s["body"][1]

        frontier = {head}
        for _ in range(steps):
            next_frontier = set()
            for pos in frontier:
                for nxt in neighbors(pos, w, h):
                    if nxt == forbidden or nxt in body:
                        continue
                    if nxt in danger:
                        continue
                    next_frontier.add(nxt)
            danger.update(next_frontier)
            if not next_frontier:
                break
            frontier = next_frontier

    return danger


def likely_enemy_star_zones(snakes, stars, obstacles, w, h, my_head):
    if not stars:
        return set()

    danger = set()
    for star in stars:
        target = star["pos"]
        our_dist = torus_dist(my_head, target, w, h)
        for s in snakes:
            head = s["head"]
            if head == my_head:
                continue
            enemy_dist = torus_dist(head, target, w, h)
            if enemy_dist <= our_dist + STAR_RACE_MARGIN:
                body_obstacles = obstacles | set(s.get("body", []))
                path_first, path_len, path = astar(head, target, body_obstacles, w, h)
                if path:
                    danger.update(path)
                    for pos in path:
                        for nxt in neighbors(pos, w, h):
                            danger.add(nxt)
    return danger


def enemy_body_and_head_zones(snakes):
    zones = set()
    for s in snakes:
        zones.add(s["head"])
        zones.update(s.get("body", []))
    return zones


# ========== MOVE CONVERSION ==========
def move_from_step(step, head, w, h):
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


# ========== SPACE CALCULATION ==========
def reachable_space(start, obstacles, w, h, limit=500):
    seen = {start}
    queue = [start]
    count = 0

    while queue and count < limit:
        current = queue.pop(0)
        count += 1
        for nxt in neighbors(current, w, h):
            if nxt in seen or nxt in obstacles:
                continue
            seen.add(nxt)
            queue.append(nxt)

    return count


def find_powered_attack_move(my_head, own_body, snakes, good_apples, bad_positions, enemy_zones, w, h, safe_moves, remaining_boost):
    enemy_targets = []
    for s in snakes:
        if s["head"] == my_head:
            continue
        body = s.get("body", [])
        for idx, cell in enumerate(body):
            enemy_targets.append({
                "pos": cell,
                "type": "head" if idx == 0 else "body",
                "length": len(body),
            })

    enemy_positions = {t["pos"] for t in enemy_targets}

    for move, pos in safe_moves.items():
        if pos in enemy_positions and pos not in own_body:
            return move

    best_move = None
    best_score = -1e9
    for move, pos in safe_moves.items():
        if pos in own_body:
            continue

        dist_map = {pos: 0}
        queue = [pos]
        while queue:
            current = queue.pop(0)
            d = dist_map[current]
            if d >= 2:
                continue
            for nxt in neighbors(current, w, h):
                if nxt in dist_map or nxt in own_body:
                    continue
                dist_map[nxt] = d + 1
                queue.append(nxt)

        move_score = 0
        for target in enemy_targets:
            if target["pos"] in dist_map:
                d = dist_map[target["pos"]]
                if d <= 2:
                    move_score += POWERED_KILL_REWARD
                    move_score += 220 if target["type"] == "head" else 90
                    move_score += target["length"] * 12
                    move_score += 150 if d == 1 else 70
                    move_score -= d * 30

        move_score += reachable_space(pos, own_body, w, h) * 2
        if remaining_boost <= BOOST_END_SAFETY_MARGIN:
            move_score += escape_score(pos, own_body, w, h) * 8
            move_score -= 140

        if pos in bad_positions:
            move_score -= BAD_APPLE_PENALTY

        if pos in enemy_zones:
            move_score += 30

        if move_score > best_score:
            best_score = move_score
            best_move = move

    return best_move


# ========== GOOD APPLE TARGETING ==========
def find_safe_good_apple_move(my_head, good_apples, obstacles, enemy_zones, snakes, w, h, safe_moves):
    if not good_apples:
        return None

    enemy_heads = [s["head"] for s in snakes if s["head"] != my_head]
    if not enemy_heads:
        enemy_heads = [my_head]

    best_move = None
    best_score = -1e9
    for apple in good_apples:
        target = apple["pos"]
        if target in enemy_zones:
            continue

        path_obstacles = obstacles | enemy_zones
        first_step, path_len, path = astar(my_head, target, path_obstacles, w, h)
        if first_step is None:
            continue
        if first_step in enemy_zones:
            continue

        enemy_dist = min(torus_dist(head, target, w, h) for head in enemy_heads)
        if path_len > enemy_dist + 1:
            continue

        reward = apple["value"] * 150
        distance_penalty = path_len * 8
        enemy_margin = max(0, enemy_dist - path_len) * 40
        score = reward - distance_penalty + enemy_margin

        if score > best_score and first_step in safe_moves.values():
            best_score = score
            best_move = move_from_step(first_step, my_head, w, h)

    return best_move


def find_best_star_move(my_head, obstacles, snakes, stars, bad_positions, enemy_zones, w, h, safe_moves):
    if not stars:
        return None

    own_body = set(next((s["body"] for s in snakes if s["head"] == my_head), []))
    enemy_bodies = set()
    enemy_heads = []
    for s in snakes:
        if s["head"] == my_head:
            continue
        enemy_heads.append(s["head"])
        enemy_bodies.update(s.get("body", []))

    blocked = own_body | enemy_bodies | set(enemy_heads)
    best_move = None
    best_score = -1e9
    best_metrics = None

    for star in stars:
        target = star["pos"]
        my_len, my_bad, my_danger, first_step, path = shortest_star_path(
            my_head,
            target,
            blocked,
            bad_positions,
            enemy_zones,
            w,
            h,
        )
        if my_len is None:
            continue

        enemy_min = 1e9
        for head in enemy_heads:
            enemy_len, _, _, _, _ = shortest_star_path(
                head,
                target,
                blocked,
                bad_positions,
                enemy_zones,
                w,
                h,
            )
            if enemy_len is not None:
                enemy_min = min(enemy_min, enemy_len)

        if enemy_min == 1e9:
            enemy_min = my_len + 1

        if my_len >= enemy_min:
            continue

        open_space = reachable_space(target, obstacles, w, h)
        score = STAR_REWARD - my_len * 30 - my_bad * 18 - my_danger * 36 + open_space * 2

        if score > best_score or (
            score == best_score and best_metrics is not None and (
                my_bad < best_metrics["bad"] or
                (my_bad == best_metrics["bad"] and open_space > best_metrics["open_space"]) or
                (my_bad == best_metrics["bad"] and open_space == best_metrics["open_space"] and my_len < best_metrics["len"]) 
            )
        ):
            if first_step in safe_moves.values():
                best_score = score
                best_move = move_from_step(first_step, my_head, w, h)
                best_metrics = {"bad": my_bad, "open_space": open_space, "len": my_len}

    return best_move


def avoid_contested_star_move(my_head, obstacles, snakes, stars, bad_positions, enemy_zones, w, h, safe_moves):
    contested = []
    for star in stars:
        target = star["pos"]
        our_dist = torus_dist(my_head, target, w, h)
        enemy_dist = min((torus_dist(s["head"], target, w, h) for s in snakes if s["head"] != my_head), default=999)
        if enemy_dist <= our_dist:
            contested.append(target)

    if not contested:
        return None

    best_move = None
    best_score = -1e9
    for move, pos in safe_moves.items():
        score = 0
        score += sum(torus_dist(pos, star, w, h) for star in contested) * 4
        score += sum(torus_dist(pos, s["head"], w, h) for s in snakes if s["head"] != my_head) * 2
        if pos in enemy_zones:
            score -= ENEMY_DANGER_PENALTY
        if pos in bad_positions:
            score -= BAD_APPLE_PENALTY
        if score > best_score:
            best_score = score
            best_move = move
    return best_move


def score_move(pos, move, obstacles, bad_positions, enemy_zones, good_apples, current_direction, w, h, star_targets):
    score = 0
    search_obstacles = obstacles | enemy_zones
    survival_space = reachable_space(pos, search_obstacles, w, h, limit=300)
    score += survival_space * OPEN_SPACE_WEIGHT

    escape = escape_score(pos, obstacles, w, h)
    score += escape * 8
    if escape <= 1:
        score -= 100

    if pos in enemy_zones:
        score -= ENEMY_DANGER_PENALTY

    if good_apples:
        nearest = min(torus_dist(pos, apple["pos"], w, h) for apple in good_apples)
        score += 40 / (nearest + 1)
        if any(torus_dist(pos, apple["pos"], w, h) == 1 for apple in good_apples):
            score += 90

    if pos in bad_positions:
        score -= BAD_APPLE_PENALTY
    if is_adjacent_to_bad(pos, bad_positions, w, h):
        score -= 20

    if move == current_direction:
        score += 10

    open_neighbors = sum(1 for nxt in neighbors(pos, w, h) if nxt not in obstacles)
    score += open_neighbors * 4

    for star in star_targets:
        score += -12 / (torus_dist(pos, star["pos"], w, h) + 1)

    return score


def find_powered_attack_move(my_head, obstacles, snakes, good_apples, bad_positions, enemy_zones, w, h, safe_moves, remaining_boost):
    enemy_positions = []
    for s in snakes:
        if s["head"] == my_head:
            continue
        enemy_positions.append(s["head"])
        enemy_positions.extend(s.get("body", []))

    best_move = None
    best_score = -1e9
    for move, pos in safe_moves.items():
        score = 0
        if pos in enemy_positions:
            score += POWERED_KILL_REWARD * 1.5

        distance_to_enemy = min((torus_dist(pos, enemy, w, h) for enemy in enemy_positions), default=999)
        score += max(0, 80 - distance_to_enemy * 8)

        open_space = reachable_space(pos, obstacles, w, h, limit=300)
        score += open_space * 2.5

        if remaining_boost <= BOOST_END_SAFETY_MARGIN:
            score -= 120
            score += escape_score(pos, obstacles, w, h) * 6

        if pos in bad_positions:
            score -= BAD_APPLE_PENALTY

        if good_apples:
            nearest_apple = min(torus_dist(pos, apple["pos"], w, h) for apple in good_apples)
            score += 20 / (nearest_apple + 1)

        if pos in enemy_zones:
            score += 30

        if score > best_score:
            best_score = score
            best_move = move
    return best_move


# ========== MAIN STRATEGY ==========
def choose_next_move(my_head, obstacles, snakes, field_size, items, current_direction, my_effects=None):
    w, h = field_size
    hx, hy = my_head

    def wrap(x, y):
        return (x % w, y % h)

    moves = {
        "NORTH": wrap(hx, hy - 1),
        "SOUTH": wrap(hx, hy + 1),
        "EAST": wrap(hx + 1, hy),
        "WEST": wrap(hx - 1, hy),
    }

    opposite = {
        "NORTH": "SOUTH",
        "SOUTH": "NORTH",
        "EAST": "WEST",
        "WEST": "EAST",
    }

    forbidden = opposite.get(current_direction)

    safe_moves = {
        d: pos for d, pos in moves.items()
        if d != forbidden and is_safe(pos, obstacles, w, h)
    }
    if not safe_moves:
        return current_direction

    good_apples, bad_apples, stars = classify_items(items)
    bad_positions = {apple["pos"] for apple in bad_apples}
    enemy_zones = predicted_enemy_zones(snakes, obstacles, w, h, my_head, steps=3)
    contested_zones = likely_enemy_star_zones(snakes, stars, obstacles, w, h, my_head)
    enemy_zones |= contested_zones

    my_body = set(next((s["body"] for s in snakes if s["head"] == my_head), []))
    powered = snake_has_power({"active_effects": my_effects}) if my_effects is not None else False
    remaining_boost = power_remaining(my_effects) if my_effects is not None else 0

    if powered:
        powered_moves = {
            d: p for d, p in moves.items()
            if d != forbidden and p not in my_body
        }
        powered_move = find_powered_attack_move(
            my_head,
            my_body,
            snakes,
            good_apples,
            bad_positions,
            enemy_zones,
            w,
            h,
            powered_moves,
            remaining_boost,
        )
        if powered_move:
            return powered_move

    if not powered and stars:
        star_move = find_best_star_move(
            my_head,
            obstacles,
            snakes,
            stars,
            bad_positions,
            enemy_zones,
            w,
            h,
            safe_moves,
        )
        if star_move:
            return star_move

        avoid_move = avoid_contested_star_move(
            my_head,
            obstacles,
            snakes,
            stars,
            bad_positions,
            enemy_zones,
            w,
            h,
            safe_moves,
        )
        if avoid_move:
            return avoid_move

    apple_move = find_safe_good_apple_move(
        my_head,
        good_apples,
        obstacles,
        enemy_zones,
        snakes,
        w,
        h,
        safe_moves,
    )
    if apple_move:
        return apple_move

    best_move = None
    best_score = -1e9
    for move, pos in safe_moves.items():
        score = score_move(
            pos,
            move,
            obstacles,
            bad_positions,
            enemy_zones,
            good_apples,
            current_direction,
            w,
            h,
            stars,
        )
        if score > best_score:
            best_score = score
            best_move = move

    return best_move
