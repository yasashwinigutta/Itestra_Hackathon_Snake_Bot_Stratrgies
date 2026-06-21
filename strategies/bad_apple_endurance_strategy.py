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


# ---------------- 2 STEP SAFETY ----------------
def is_safe(pos, obstacles, w, h):
    if pos in obstacles:
        return False

    if escape_score(pos, obstacles, w, h) <= 1:
        return False

    return True


# ---------------- A* ----------------
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
        return None

    cur = goal
    while came[cur] != start:
        cur = came[cur]

    return cur


# ---------------- ENEMY PREDICTION ----------------
def predicted_enemy_zones(snakes, obstacles, w, h):
    zones = set()

    for s in snakes:
        head = s["head"]
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

        zones.update(first_steps)

        for step in first_steps:
            for nxt in neighbors(step, w, h):
                if nxt in body or nxt == head:
                    continue
                zones.add(nxt)

    return zones


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


# ---------------- CENTER REGION ----------------
def center_region(center, radius, point):
    return manhattan(center, point) <= radius


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

    apples = [(i.position[0], i.position[1]) for i in items if i.kind == "Apple"]
    bad = [(i.position[0], i.position[1]) for i in items if i.kind == "BadApple"]
    enemy_zones = predicted_enemy_zones(snakes, obstacles, w, h)

    center = ((w - 1) // 2, (h - 1) // 2)
    center_radius = max(3, min(w, h) // 5)
    center_apples = [a for a in apples if center_region(center, center_radius, a)]

    for d, pos in safe_moves.items():
        if pos in apples:
            return d

    def apple_priority(target):
        dist = torus_dist(my_head, target, w, h)
        score = -dist
        if target in enemy_zones:
            score -= 100
        if center_region(center, center_radius, target):
            score += 40
        return score

    def choose_path_target(targets):
        for target in sorted(targets, key=lambda a: apple_priority(a), reverse=True):
            if target in enemy_zones:
                continue
            step = astar(my_head, target, obstacles, w, h)
            if not step:
                continue
            if not is_safe(step, obstacles, w, h):
                continue
            if step in enemy_zones:
                continue
            move = move_from_step(step, my_head, w, h)
            if move in safe_moves:
                return move
        return None

    if center_apples and len(center_apples) >= max(3, center_radius // 2):
        move = choose_path_target(center_apples)
        if move:
            return move

    if apples:
        move = choose_path_target(apples)
        if move:
            return move

    best_move = None
    best_score = -1e9

    for d, pos in safe_moves.items():
        score = 0

        for ax, ay in apples:
            dist = torus_dist(pos, (ax, ay), w, h)
            bonus = 150 / (dist + 1)
            if center_region(center, center_radius, (ax, ay)):
                bonus *= 1.6
            score += bonus

        for bx, by in bad:
            dist = torus_dist(pos, (bx, by), w, h)
            score -= 140 / (dist + 1)

        if pos in enemy_zones:
            score -= 180
        if any(torus_dist(pos, zone, w, h) == 1 for zone in enemy_zones):
            score -= 50

        for s in snakes:
            ex, ey = s["head"]
            dist = torus_dist(pos, (ex, ey), w, h)
            if dist == 1:
                score -= 120
            elif dist == 2:
                score -= 35
            score += dist * 0.2

        if center_apples and len(center_apples) > max(2, center_radius // 3):
            score += 12 if center_region(center, center_radius, pos) else 0

        score += sum(
            1 for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]
            if wrap(pos[0] + dx, pos[1] + dy) not in obstacles
        ) * 1.8

        if d == current_direction:
            score += 6

        if score > best_score:
            best_score = score
            best_move = d

    return best_move
