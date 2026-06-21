import heapq
from collections import deque

# ================= DIST =================
def dist(a, b, w, h):
    return min(abs(a[0]-b[0]), w-abs(a[0]-b[0])) + \
           min(abs(a[1]-b[1]), h-abs(a[1]-b[1]))


# ================= NEIGHBORS =================
def neighbors(p, w, h):
    x, y = p
    return [
        ((x+1)%w, y),
        ((x-1)%w, y),
        (x, (y+1)%h),
        (x, (y-1)%h),
    ]


# ================= BFS PATH COST =================
def bfs_path(start, goal, obstacles, w, h):
    q = deque([(start, 0, 0)])  # (pos, dist, bad_apples_on_path)
    seen = {start}

    while q:
        cur, d, bad = q.popleft()

        if cur == goal:
            return d, bad

        for n in neighbors(cur, w, h):
            if n in seen:
                continue
            seen.add(n)

            new_bad = bad + (1 if n in obstacles else 0)
            q.append((n, d+1, new_bad))

    return None, None


# ================= KILL DETECTION =================
def get_kill_targets(my_head, snakes):
    targets = []
    for s in snakes:
        d = dist(my_head, s["head"], len(s["body"]), len(s["body"]))
        if d <= 3:
            targets.append((s["head"], d))
    return targets


# ================= STAR RACE =================
def star_winner(my_head, star, snakes, w, h):
    my_d = dist(my_head, star, w, h)

    for s in snakes:
        if dist(s["head"], star, w, h) <= my_d:
            return False  # someone can tie or beat you

    return True


# ================= MOVE GENERATION =================
def choose_next_move(my_head, obstacles, snakes, field_size, items, current_direction):

    w, h = field_size
    hx, hy = my_head

    def wrap(x, y):
        return (x % w, y % h)

    moves = {
        "NORTH": wrap(hx, hy-1),
        "SOUTH": wrap(hx, hy+1),
        "EAST": wrap(hx+1, hy),
        "WEST": wrap(hx-1, hy),
    }

    opposite = {
        "NORTH":"SOUTH","SOUTH":"NORTH",
        "EAST":"WEST","WEST":"EAST"
    }

    forbidden = opposite.get(current_direction)

    safe_moves = {
        d:p for d,p in moves.items()
        if d != forbidden
    }

    if not safe_moves:
        return current_direction

    apples = [(i.position[0], i.position[1]) for i in items if i.kind == "Apple"]
    stars  = [(i.position[0], i.position[1]) for i in items if i.kind == "Star"]

    # ================= KILL MODE =================
    kill_targets = get_kill_targets(my_head, snakes)

    best_move = None
    best_score = -1e18

    # star pre-check
    best_star = None
    if stars:
        best_star = min(stars, key=lambda s: dist(my_head, s, w, h))

    for d, pos in safe_moves.items():

        score = 0

        # ================= 1. KILL FORCE =================
        for t, kd in kill_targets:
            d_to = dist(pos, t, w, h)

            if kd == 1:
                score += 1000
            elif kd == 2:
                score += 400 / (d_to + 1)
            elif kd == 3:
                score += 120 / (d_to + 1)

        # ================= 2. STAR RACE WIN CHECK =================
        if best_star:
            if star_winner(my_head, best_star, snakes, w, h):
                score += (dist(my_head, best_star, w, h) - dist(pos, best_star, w, h)) * 150

        # ================= 3. APPLE OPTIMIZATION =================
        if apples:
            best_apple = min(apples, key=lambda a: dist(pos, a, w, h))
            score += 120 / (dist(pos, best_apple, w, h) + 1)

        # ================= 4. PATH QUALITY =================
        for target in ([best_star] if best_star else []):
            if target:
                path_len, bad_cnt = bfs_path(pos, target, obstacles, w, h)
                if path_len:
                    score += 200 / (path_len + 1)
                    score -= bad_cnt * 10  # tie-break only

        # ================= 5. SURVIVAL =================
        score += sum(1 for n in neighbors(pos, w, h) if n not in obstacles) * 6

        # ================= 6. RISK =================
        for s in snakes:
            score -= max(0, 100 - dist(pos, s["head"], w, h) * 25)

        # ================= 7. LOOP BREAK =================
        if hasattr(choose_next_move, "prev") and pos == choose_next_move.prev:
            score -= 60

        if score > best_score:
            best_score = score
            best_move = d

    choose_next_move.prev = my_head
    return best_move