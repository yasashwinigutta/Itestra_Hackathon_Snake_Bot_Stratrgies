from collections import deque

# ==========================================================
# SIMPLE COLLECT & RUN AWAY STRATEGY
# ==========================================================

DIRECTIONS = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "WEST": (-1, 0),
    "EAST": (1, 0),
}

OPPOSITE = {
    "NORTH": "SOUTH",
    "SOUTH": "NORTH",
    "WEST": "EAST",
    "EAST": "WEST",
}

# ==========================================================
# HELPERS
# ==========================================================

def add(a, b):
    return (a[0] + b[0], a[1] + b[1])

def wrap(p, w, h):
    return (p[0] % w, p[1] % h)

def dist(a, b, w, h):
    return min(abs(a[0]-b[0]), w-abs(a[0]-b[0])) + \
           min(abs(a[1]-b[1]), h-abs(a[1]-b[1]))

def flood_fill(start, blocked, size, limit=300):
    if start in blocked:
        return 0
    w, h = size
    q = deque([start])
    seen = {start}
    c = 0
    while q and c < limit:
        cur = q.popleft()
        c += 1
        for d in DIRECTIONS.values():
            nxt = wrap(add(cur, d), w, h)
            if nxt in blocked or nxt in seen:
                continue
            seen.add(nxt)
            q.append(nxt)
    return c

def classify(items):
    swords, boosts = [], []
    for it in items:
        kind = str(it.kind).lower()
        if "sword" in kind:
            swords.append(it.position)
        elif "boost" in kind:
            boosts.append(it.position)
    return swords, boosts

# ==========================================================
# STATE
# ==========================================================

_tick = 0
_last_boost = -100
_last_sword = -100
_attack_mode = False  # True = attacking a body, False = safe mode
_current_target = None  # (enemy_head, body_pos) being attacked
_safe_mode_until = 0  # tick until we exit safe mode


# ==========================================================
# MAIN STRATEGY: COLLECT BOOSTS & SWORDS, RUN AWAY
# ==========================================================

def choose_next_move(my_head, obstacles, snakes, size, items, direction):
    global _tick, _last_boost, _last_sword, _attack_cooldown
    _tick += 1

    w, h = size

    my_snake = next((s for s in snakes if s["head"] == my_head), None)
    my_body = set(my_snake.get("body", [])) if my_snake else set()
    my_body_no_head = set(b for b in my_body if b != my_head)

    inventory = my_snake.get("inventory", []) if my_snake else []
    boosts_owned = sum("boost" in str(i).lower() for i in inventory)
    swords_owned = sum("sword" in str(i).lower() for i in inventory)

    swords, boosts = classify(items)

    blocked = obstacles | my_body_no_head

    # ======================================================
    # ENEMY SCAN
    # ======================================================
    enemy_heads = [s["head"] for s in snakes if s["head"] != my_head]
    nearest_enemy = min(enemy_heads, key=lambda p: dist(my_head, p, w, h)) if enemy_heads else None
    nearest_enemy_dist = dist(my_head, nearest_enemy, w, h) if nearest_enemy else 999

    # ======================================================
    # ATTACK STATE
    # ======================================================
    if "_attack_state" not in globals():
        global _attack_state, _attack_target, _attack_cooldown
        _attack_state = False
        _attack_target = None
        _attack_cooldown = 0

    if _attack_cooldown > 0:
        _attack_cooldown -= 1
        _attack_state = False

    # enter attack mode
    if swords_owned >= 3 and nearest_enemy_dist <= 6 and _attack_cooldown == 0:
        _attack_state = True
        _attack_target = nearest_enemy

    # exit attack if enemy turns aggressive toward us
    if nearest_enemy_dist <= 3:
        _attack_state = False
        _attack_cooldown = 6

    # ======================================================
    # FIND CUT POSITION (REAL KILL CELL)
    # ======================================================
    cut_move = None
    if _attack_state:
        for move, d in DIRECTIONS.items():
            nxt = wrap(add(my_head, d), w, h)

            for s in snakes:
                if s["head"] == my_head:
                    continue
                body = s.get("body", [])

                # try cutting body
                for i in range(1, len(body)):
                    if body[i] == nxt:
                        cut_move = move
                        break

    # ======================================================
    # SAFE MODE SCORE
    # ======================================================
    best_move = direction
    best_score = -1e18

    for move, d in DIRECTIONS.items():

        if move == OPPOSITE.get(direction):
            continue

        nxt = wrap(add(my_head, d), w, h)

        if nxt in blocked:
            continue

        score = 0

        space = flood_fill(nxt, blocked, size)
        score += space * 8

        if nearest_enemy:
            score -= max(0, 6 - dist(nxt, nearest_enemy, w, h)) * 300

        # ==================================================
        # ATTACK MODE PRIORITY
        # ==================================================
        if _attack_state:
            score += 1500

            if cut_move and move == cut_move:
                score += 1e6  # forced cut alignment

        # ==================================================
        # BOOST LOGIC
        # ==================================================
        if boosts:
            nearest_boost = min(boosts, key=lambda p: dist(my_head, p, w, h))
            score += -dist(nxt, nearest_boost, w, h) * 6

        # ==================================================
        # SWORD LOGIC (simple trigger only)
        # ==================================================
        if swords:
            nearest_sword = min(swords, key=lambda p: dist(my_head, p, w, h))
            if dist(my_head, nearest_sword, w, h) == 1:
                activate = "SWORD"

        if score > best_score:
            best_score = score
            best_move = move

    # ======================================================
    # ACTION DECISION
    # ======================================================
    activate = None

    # BOOST: escape or reposition in attack mode
    if boosts_owned >= 3 and nearest_enemy_dist <= 5:
        activate = "BOOST"
        _last_boost = _tick

    # SWORD: only if attack mode OR forced cut exists
    if swords_owned >= 3 and (_attack_state or cut_move):
        if _tick - _last_sword > 5:
            activate = "SWORD"
            _last_sword = _tick

    return best_move, activate