import heapq


# ================= DIST =================
def dist(a, b, w, h):
    return min(abs(a[0] - b[0]), w - abs(a[0] - b[0])) + \
           min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))


# ================= NEIGHBORS =================
def neighbors(p, w, h):
    x, y = p
    return [
        ((x + 1) % w, y),
        ((x - 1) % w, y),
        (x, (y + 1) % h),
        (x, (y - 1) % h),
    ]


# ================= KILL WINDOW =================
def detect_kill_target(my_head, snakes, w, h):
    candidates = []

    for s in snakes:
        d = dist(my_head, s["head"], w, h)

        # kill window = must be within 3 steps
        if 1 <= d <= 3:
            candidates.append((s["head"], d))

    if not candidates:
        return None

    return min(candidates, key=lambda x: x[1])[0]


# ================= MOVE HELPER =================
def choose_step(cur, target, w, h):
    best = None
    best_d = 1e9

    for n in neighbors(cur, w, h):
        d = dist(n, target, w, h)
        if d < best_d:
            best_d = d
            best = n

    return best


# ================= MAIN =================
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
        if d != forbidden and pos not in obstacles
    }

    if not safe_moves:
        return current_direction

    # ================= INIT KILL PLAN =================
    if not hasattr(choose_next_move, "kill_plan"):
        choose_next_move.kill_plan = None

    # ================= CHECK / REFRESH KILL PLAN =================
    kill_target = detect_kill_target(my_head, snakes, w, h)

    if kill_target:
        if (choose_next_move.kill_plan is None or
            choose_next_move.kill_plan["target"] != kill_target):

            choose_next_move.kill_plan = {
                "target": kill_target,
                "ticks": 3
            }

    # invalidate if target gone
    if choose_next_move.kill_plan:
        alive_heads = [s["head"] for s in snakes]
        if choose_next_move.kill_plan["target"] not in alive_heads:
            choose_next_move.kill_plan = None

    # ================= FORCE KILL MODE =================
    if choose_next_move.kill_plan:

        target = choose_next_move.kill_plan["target"]
        choose_next_move.kill_plan["ticks"] -= 1

        best_move = None
        best_score = -1e18

        for d, pos in safe_moves.items():

            score = 0

            # strong attraction to target
            score += (dist(my_head, target, w, h) -
                      dist(pos, target, w, h)) * 200

            # cut-off bonus (get side positioning)
            score += sum(
                50 for n in neighbors(pos, w, h)
                if dist(n, target, w, h) < dist(pos, target, w, h)
            )

            # mild risk penalty
            score -= sum(
                100 for s in snakes
                if dist(pos, s["head"], w, h) <= 1
            )

            if score > best_score:
                best_score = score
                best_move = d

        # end plan after 3 forced moves
        if choose_next_move.kill_plan["ticks"] <= 0:
            choose_next_move.kill_plan = None

        return best_move

    # ================= NORMAL MODE (FARM) =================
    stars = [(i.position[0], i.position[1]) for i in items if i.kind == "Star"]
    apples = [(i.position[0], i.position[1]) for i in items if i.kind == "Apple"]

    def apple_score(pos):
        if not apples:
            return 0
        d = min(dist(pos, a, w, h) for a in apples)
        return 70 / (d + 1)

    best_move = None
    best_score = -1e18

    for d, pos in safe_moves.items():

        score = 0

        # survival baseline
        score -= sum(
            100 for s in snakes
            if dist(pos, s["head"], w, h) <= 2
        )

        # star (ONLY if no kill plan)
        if stars:
            best_star = min(stars, key=lambda s: dist(my_head, s, w, h))
            score += (dist(my_head, best_star, w, h) -
                      dist(pos, best_star, w, h)) * 80

        # apple fallback
        else:
            score += apple_score(pos)

        # anti-loop
        if hasattr(choose_next_move, "prev") and pos == choose_next_move.prev:
            score -= 20

        if score > best_score:
            best_score = score
            best_move = d

    choose_next_move.prev = my_head
    return best_move