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


# ---------------- ENEMY HEAD PREDICTION / DANGER ZONES ----------------
def enemy_head_danger_zones(snakes, w, h, depth=3):
    """Return dicts for head reachable cells at depths 1..depth and near-radius sets.
    Returns: {
        'head_current': set(),
        'reach_1': set(),
        'reach_2': set(),
        'reach_3': set(),
        'near_radius_1': set(),
        'near_radius_2': set()
    }
    """
    head_current = set()
    reach = {1: set(), 2: set(), 3: set()}
    near1 = set()
    near2 = set()

    def wrap(p):
        return (p[0] % w, p[1] % h)

    for s in snakes:
        head = tuple(s["head"])
        body = [tuple(b) for b in s.get("body", [])]
        head_current.add(head)

        # near radii
        for x in range(w):
            pass
        # generate neighbors for depth 1
        neck = body[1] if len(body) >= 2 else None
        first = [n for n in neighbors(head, w, h) if n != neck and n not in body]
        if not first:
            first = [n for n in neighbors(head, w, h) if n != neck]
        reach[1].update(first)

        # depth expansions
        frontier = set(first)
        visited = set(frontier) | {head}
        for d in range(2, depth + 1):
            next_front = set()
            for cell in frontier:
                for nb in neighbors(cell, w, h):
                    if nb in visited:
                        continue
                    next_front.add(nb)
                    visited.add(nb)
            reach[d].update(next_front)
            frontier = next_front

        # near radius sets (torus distance <=1 and <=2)
        for x in range(w):
            for y in range(h):
                p = (x, y)
                d = torus_dist(head, p, w, h)
                if d <= 1:
                    near1.add(p)
                if d <= 2:
                    near2.add(p)

    return {
        'head_current': head_current,
        'reach_1': reach[1],
        'reach_2': reach[2],
        'reach_3': reach[3],
        'near_radius_1': near1,
        'near_radius_2': near2,
    }


# ---------------- RISK-AWARE A* (path costs consider danger) ----------------
def risk_aware_astar(start, goal, snakes, obstacles, items, w, h, danger_info):
    """A* that applies penalties for danger zones and bad apples. Returns path list or None."""
    bad_apples = {tuple(i.position) for i in items if getattr(i, 'kind', '') == 'BadApple'}
    enemy_bodies = set()
    for s in snakes:
        enemy_bodies.update([tuple(b) for b in s.get('body', [])])

    def cost_for(cell):
        c = 1
        if cell in bad_apples:
            c += 6
        # heavy penalties for reach_1 and near1
        if cell in danger_info['head_current']:
            return None  # treat as blocked
        if cell in danger_info['reach_1'] or cell in danger_info['near_radius_1']:
            c += 1000
        elif cell in danger_info['reach_2'] or cell in danger_info['near_radius_2']:
            c += 300
        elif cell in danger_info['reach_3']:
            c += 120
        return c

    def heuristic(a, b):
        return torus_dist(a, b, w, h)

    open_set = [(heuristic(start, goal), 0, start)]
    came = {}
    gscore = {start: 0}

    while open_set:
        _, g, cur = heapq.heappop(open_set)
        if cur == goal:
            # reconstruct
            path = [cur]
            while path[-1] != start:
                path.append(came[path[-1]])
            path.reverse()
            return path

        for nb in neighbors(cur, w, h):
            if nb in obstacles and nb != goal:
                continue
            if nb in enemy_bodies and nb != goal:
                continue
            cell_cost = cost_for(nb)
            if cell_cost is None:
                continue
            tentative = g + cell_cost
            if nb not in gscore or tentative < gscore[nb]:
                gscore[nb] = tentative
                came[nb] = cur
                heapq.heappush(open_set, (tentative + heuristic(nb, goal), tentative, nb))

    return None


# ---------------- CELL RISK / SAFE CHECKS ----------------
def is_fully_safe_move(pos, snakes, obstacles, danger_info, w, h, powered=False):
    # own body
    for s in snakes:
        if pos in [tuple(x) for x in s.get('body', [])]:
            # if it's our body and powered maybe allowed? treat as blocked
            return False

    # enemy head current or reach_1 are considered unsafe unless powered
    if not powered and (pos in danger_info['head_current'] or pos in danger_info['reach_1'] or pos in danger_info['near_radius_1']):
        return False

    # prefer to avoid reach_2
    if not powered and pos in danger_info['reach_2']:
        return False

    # escape options
    # build obstacles set for escape_score
    obs = set()
    for s in snakes:
        obs.update([tuple(x) for x in s.get('body', [])])
    # add stationary obstacles
    obs |= set(obstacles)
    if escape_score(pos, obs, w, h) <= 1:
        return False

    return True


def is_emergency_safe_move(pos, snakes, obstacles, danger_info, w, h, powered=False):
    # allow reach_2 but not reach_1
    for s in snakes:
        if pos in [tuple(x) for x in s.get('body', [])]:
            return False
    if not powered and (pos in danger_info['head_current'] or pos in danger_info['reach_1'] or pos in danger_info['near_radius_1']):
        return False
    # allow reach_2
    obs = set()
    for s in snakes:
        obs.update([tuple(x) for x in s.get('body', [])])
    obs |= set(obstacles)
    return escape_score(pos, obs, w, h) >= 1


# ---------------- MAIN STRATEGY (UPDATED) ----------------


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

    # compute enemy head danger info
    danger_info = enemy_head_danger_zones(snakes, w, h, depth=3)

    # collect apples and bad apples as tuples
    apples = [tuple((i.position[0], i.position[1])) for i in items if i.kind == "Apple"]
    bad = [tuple((i.position[0], i.position[1])) for i in items if i.kind == "BadApple"]

    center = ((w - 1) // 2, (h - 1) // 2)
    center_radius = max(3, min(w, h) // 5)
    center_apples = [a for a in apples if center_region(center, center_radius, a)]

    # build obstacles including bodies
    body_obstacles = set(obstacles)
    for s in snakes:
        for seg in s.get("body", []):
            body_obstacles.add(tuple(seg))

    # candidate moves (avoid reverse)
    candidates = {d: pos for d, pos in moves.items() if d != forbidden}

    # filter out immediate illegal collision moves (onto bodies)
    legal = {d: p for d, p in candidates.items() if p not in body_obstacles}
    if not legal:
        # no legal non-body moves: allow current_direction if exists
        return current_direction

    # avoid moves that equal enemy immediate next head positions if alternatives exist
    immediate = danger_info['reach_1']
    non_crash = {d: p for d, p in legal.items() if p not in immediate}

    # prefer non-crash moves; if none, keep legal
    options = non_crash if non_crash else legal

    # prefer moves that are fully safe per definition
    powered = False  # we don't have snake state here; assume not powered
    fully_safe = {d: p for d, p in options.items() if is_fully_safe_move(p, snakes, obstacles, danger_info, w, h, powered=powered)}
    if fully_safe:
        options = fully_safe

    # immediate adjacent apple take if safe
    for d, p in list(options.items()):
        if p in apples and is_fully_safe_move(p, snakes, obstacles, danger_info, w, h, powered=powered):
            return d

    # path targets: center apples prioritized
    def apple_value(path):
        if not path:
            return -1e9
        # value based on length and danger along path
        path_danger = sum(1 for c in path if c in danger_info['reach_1'])
        bads_on_path = sum(1 for c in path if c in bad)
        return - (len(path) + path_danger * 5 + bads_on_path * 6)

    def choose_path_target(targets):
        best = None
        best_score = -1e9
        for target in targets:
            path = risk_aware_astar(my_head, target, snakes, body_obstacles, items, w, h, danger_info)
            if not path:
                continue
            sc = apple_value(path)
            if sc > best_score:
                best_score = sc
                best = path
        return best

    if center_apples and len(center_apples) >= max(3, center_radius // 2):
        path = choose_path_target(center_apples)
        if path and len(path) >= 2:
            move = move_from_step(path[1], my_head, w, h)
            if move in options:
                return move

    if apples:
        path = choose_path_target(apples)
        if path and len(path) >= 2:
            move = move_from_step(path[1], my_head, w, h)
            if move in options:
                return move

    # scoring for remaining options
    best_move = None
    best_score = -1e9
    for d, pos in options.items():
        score = 0

        # apple proximity
        for ax, ay in apples:
            dist = torus_dist(pos, (ax, ay), w, h)
            score += 200 / (dist + 1)

        # bad apples penalty
        for bx, by in bad:
            dist = torus_dist(pos, (bx, by), w, h)
            score -= 220 / (dist + 1)

        # immediate head radius penalties
        if pos in danger_info['near_radius_1']:
            score -= 10000
        elif pos in danger_info['near_radius_2']:
            score -= 800

        # predicted head reach penalties
        if pos in danger_info['reach_1']:
            score -= 5000
        if pos in danger_info['reach_2']:
            score -= 1200
        if pos in danger_info['reach_3']:
            score -= 400

        # proximity to enemy heads (soft)
        for s in snakes:
            ex, ey = s['head']
            dist = torus_dist(pos, (ex, ey), w, h)
            if dist == 1:
                score -= 600
            elif dist == 2:
                score -= 180

        # open space heuristic
        score += escape_score(pos, body_obstacles, w, h) * 8

        # bias to continue straight
        if d == current_direction:
            score += 10

        # dead end penalty
        if escape_score(pos, body_obstacles, w, h) <= 1:
            score -= 500

        if score > best_score:
            best_score = score
            best_move = d

    return best_move
