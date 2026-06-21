import heapq


# ---------------- TORUS DIST ----------------
def torus_dist(a, b, w, h):
    dx = min(abs(a[0] - b[0]), w - abs(a[0] - b[0]))
    dy = min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))
    return dx + dy


# ---------------- MANHATTAN ----------------
def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ---------------- NEIGHBORS ----------------
def neighbors(node, w, h):
    x, y = node
    return [
        ((x + 1) % w, y),
        ((x - 1) % w, y),
        (x, (y + 1) % h),
        (x, (y - 1) % h),
    ]


# ---------------- ESCAPE SCORE ----------------
def escape_score(pos, obstacles, w, h):
    x, y = pos
    return sum(
        ((x + dx) % w, (y + dy) % h) not in obstacles
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]
    )


# ---------------- ITEM HELPERS ----------------
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
        return -5
    if isinstance(kind, str) and "bad" in kind.lower():
        return -5
    if isinstance(kind, str) and "apple" in kind.lower():
        return 1

    return 0


def classify_items(items):
    good_apples = []
    bad_apples = []

    for item in items:
        pos = item_position(item)
        if pos is None:
            continue

        value = item_value(item)
        if value > 0:
            good_apples.append({"pos": pos, "value": value})
        else:
            bad_apples.append({"pos": pos, "value": value})

    return good_apples, bad_apples


# ---------------- SAFE CELL HELPERS ----------------
def is_safe(pos, obstacles, w, h):
    if pos in obstacles:
        return False
    if escape_score(pos, obstacles, w, h) <= 1:
        return False
    return True


def is_adjacent_to_bad(pos, bad_positions, w, h):
    return any(neighbor in bad_positions for neighbor in neighbors(pos, w, h))


# ---------------- PATH SEARCH ----------------
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

    if goal not in came:
        return None, None

    cur = goal
    while came[cur] != start:
        cur = came[cur]

    return cur, cost[goal]


# ---------------- ENEMY PREDICTION ----------------
def predicted_enemy_zones(snakes, obstacles, w, h, my_head=None):
    danger = set()

    for s in snakes:
        head = s["head"]
        if my_head is not None and head == my_head:
            continue

        body = set(s["body"])
        forbidden = None

        if len(s["body"]) >= 2:
            forbidden = s["body"][1]

        first_steps = [
            nxt for nxt in neighbors(head, w, h)
            if nxt != forbidden and nxt not in body
        ]

        if not first_steps:
            first_steps = [n for n in neighbors(head, w, h) if n != forbidden]

        danger.update(first_steps)
        for step in first_steps:
            for nxt in neighbors(step, w, h):
                if nxt in body or nxt == head:
                    continue
                danger.add(nxt)

    return danger


# ---------------- MOVE CONVERSION ----------------
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


# ---------------- SPACE CALCULATION ----------------
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


# ---------------- APPLE PATHING ----------------
def find_safe_good_apple_move(my_head, good_apples, obstacles, bad_positions, enemy_zones, snakes, w, h, safe_moves):
    best_move = None
    best_score = -1e9

    if not good_apples:
        return None

    enemy_heads = [s["head"] for s in snakes if s["head"] != my_head]
    if not enemy_heads:
        enemy_heads = [my_head]

    for apple in good_apples:
        target = apple["pos"]
        if target in enemy_zones:
            continue

        path_obstacles = obstacles | bad_positions | enemy_zones
        first_step, path_len = astar(my_head, target, path_obstacles, w, h)
        if first_step is None:
            continue

        if first_step in enemy_zones:
            continue

        enemy_dist = min(torus_dist(head, target, w, h) for head in enemy_heads)
        if path_len > enemy_dist + 1:
            continue

        reward = apple["value"] * 140
        distance_penalty = path_len * 8
        enemy_margin = max(0, enemy_dist - path_len) * 30
        score = reward - distance_penalty + enemy_margin

        if score > best_score and first_step in safe_moves.values():
            best_score = score
            best_move = move_from_step(first_step, my_head, w, h)

    return best_move


# ---------------- SURVIVAL SCORING ----------------
def score_move(pos, move, obstacles, bad_positions, bad_adjacent, enemy_zones, good_apples, current_direction, w, h):
    score = 0

    search_obstacles = obstacles | bad_positions | enemy_zones
    survival_space = reachable_space(pos, search_obstacles, w, h, limit=300)
    score += survival_space * 2
    score += escape_score(pos, obstacles, w, h) * 6

    if pos in enemy_zones:
        score -= 140
    if is_adjacent_to_bad(pos, bad_positions, w, h):
        score -= 60
    if bad_adjacent and pos in bad_adjacent:
        score -= 40

    if pos in bad_positions:
        score -= 1000

    if good_apples:
        nearest = min(torus_dist(pos, apple["pos"], w, h) for apple in good_apples)
        score += 30 / (nearest + 1)

    if move == current_direction:
        score += 12

    score -= max(0, 4 - escape_score(pos, obstacles, w, h)) * 20

    open_neighbors = sum(1 for nxt in neighbors(pos, w, h) if nxt not in obstacles)
    score += open_neighbors * 5

    return score


# ---------------- MAIN STRATEGY ----------------
def choose_next_move(my_head, obstacles, snakes, field_size, items, current_direction):
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

    good_apples, bad_apples = classify_items(items)
    bad_positions = {apple["pos"] for apple in bad_apples}
    bad_adjacent = {
        nxt for bad in bad_positions
        for nxt in neighbors(bad, w, h)
        if nxt not in bad_positions
    }

    enemy_zones = predicted_enemy_zones(snakes, obstacles, w, h, my_head)

    apple_move = find_safe_good_apple_move(
        my_head,
        good_apples,
        obstacles,
        bad_positions,
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
            bad_adjacent,
            enemy_zones,
            good_apples,
            current_direction,
            w,
            h,
        )
        if score > best_score:
            best_score = score
            best_move = move

    return best_move
