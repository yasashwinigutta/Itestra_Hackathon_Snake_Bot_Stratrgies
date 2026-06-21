import heapq


# ---------------- TORUS DIST ----------------
def torus_dist(a, b, w, h):
    dx = min(abs(a[0] - b[0]), w - abs(a[0] - b[0]))
    dy = min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))
    return dx + dy


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
        for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]
    )


# ---------------- 3 STEP SAFETY (balanced, not too strict) ----------------
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
                heapq.heappush(
                    pq,
                    (nc + torus_dist(nxt, goal, w, h), nxt)
                )

    if goal not in came:
        return None

    cur = goal
    while came[cur] != start:
        cur = came[cur]

    return cur


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

    apples = [(i.position[0], i.position[1]) for i in items if i.kind == "Apple"]
    bad = [(i.position[0], i.position[1]) for i in items if i.kind == "BadApple"]

    safe_moves = {
        d: pos for d, pos in moves.items()
        if d != forbidden and is_safe(pos, obstacles, w, h)
    }

    if not safe_moves:
        return current_direction

    # ---------------- FORCE APPLE IF DIRECT ----------------
    for d, pos in safe_moves.items():
        if pos in apples:
            return d

    # ---------------- A* PRIORITY ----------------
    if apples:
        target = min(apples, key=lambda a: torus_dist(my_head, a, w, h))
        step = astar(my_head, target, obstacles, w, h)

        if step and is_safe(step, obstacles, w, h):
            dx = (step[0] - hx) % w
            dy = (step[1] - hy) % h

            if dx == 1: return "EAST"
            if dx == w - 1: return "WEST"
            if dy == 1: return "SOUTH"
            if dy == h - 1: return "NORTH"

    # ---------------- SCORING (AGGRESSIVE) ----------------
    best_move = None
    best_score = -1e9

    for d, pos in safe_moves.items():
        score = 0

        # apple attraction
        for ax, ay in apples:
            dist = torus_dist(pos, (ax, ay), w, h)
            score += 200 / (dist + 1)

        # bad apple penalty
        for bx, by in bad:
            dist = torus_dist(pos, (bx, by), w, h)
            score -= 100 / (dist + 1)

        # enemy pressure (but not fear-based)
        for s in snakes:
            ex, ey = s["head"]
            dist = torus_dist(pos, (ex, ey), w, h)

            if dist == 1:
                score -= 80
            elif dist == 2:
                score -= 20

            score += dist * 0.15

        # open space (anti trap)
        score += sum(
            1 for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]
            if wrap(pos[0]+dx, pos[1]+dy) not in obstacles
        ) * 1.5

        if score > best_score:
            best_score = score
            best_move = d

    return best_move