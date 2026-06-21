from collections import deque

# ==========================================================
# CORE MOVES
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
_tick = 0
def _ensure_state():
    global _tick, _last_boost, _last_sword, _last_stack

    if "_tick" not in globals():
        _tick = 0
    if "_last_boost" not in globals():
        _last_boost = -100
    if "_last_sword" not in globals():
        _last_sword = -100
    if "_last_stack" not in globals():
        _last_stack = -100
# ==========================================================
# BASIC GRID HELPERS (WRAP WORLD 41x41)
# ==========================================================

def add(a, b):
    return (a[0] + b[0], a[1] + b[1])

def wrap(pos, w, h):
    return (pos[0] % w, pos[1] % h)

def wrap_dist(a, b, w, h):
    dx = min(abs(a[0] - b[0]), w - abs(a[0] - b[0]))
    dy = min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))
    return dx + dy

def neighbors(pos, w, h):
    return [wrap(add(pos, d), w, h) for d in DIRECTIONS.values()]

# ==========================================================
# FLOOD FILL (SURVIVAL SPACE ESTIMATION)
# ==========================================================

def flood_fill(start, blocked, size, limit=500):
    if start in blocked:
        return 0

    w, h = size
    q = deque([start])
    seen = {start}
    count = 0

    while q and count < limit:
        cur = q.popleft()
        count += 1

        for nxt in neighbors(cur, w, h):
            if nxt in blocked or nxt in seen:
                continue
            seen.add(nxt)
            q.append(nxt)

    return count

# ==========================================================
# ESCAPE QUALITY CHECK
# ==========================================================

def escape_options(pos, blocked, size):
    w, h = size
    return sum(1 for n in neighbors(pos, w, h) if n not in blocked)

def is_trapped(pos, blocked, size):
    return escape_options(pos, blocked, size) <= 1

# ==========================================================
# DISTANCE HELPERS
# ==========================================================

def nearest_distance(pos, targets, size):
    if not targets:
        return None
    w, h = size
    return min(wrap_dist(pos, t, w, h) for t in targets)

# ==========================================================
# ITEM CLASSIFICATION (FULL SUPPORT)
# ==========================================================

def classify_items(items):
    apples, bad, swords = [], [], []
    boosts, stars, speeds, stacks = [], [], [], []

    for it in items:
        kind = str(getattr(it, "kind", "")).lower()
        pos = getattr(it, "position", None)

        if pos is None:
            continue

        pos = (int(pos[0]), int(pos[1]))

        if "bad" in kind:
            bad.append(pos)

        elif "apple" in kind:
            apples.append(pos)

        elif "sword" in kind:
            swords.append(pos)

        elif "stack" in kind:
            stacks.append(pos)

        elif "speed" in kind:
            speeds.append(pos)

        elif "star" in kind or "shield" in kind:
            stars.append(pos)

        elif "boost" in kind:
            boosts.append(pos)

    return apples, bad, swords, boosts, stars, speeds, stacks

# ==========================================================
# BASIC SNAKE STATE HELPERS
# ==========================================================

def snake_has_keyword(snake, *keywords):
    inv = snake.get("inventory", []) or []
    eff = snake.get("active_effects", []) or []
    text = " ".join(map(str, inv + eff)).lower()
    return any(k.lower() in text for k in keywords)

def is_boosted(snake):
    return snake_has_keyword(snake, "boost", "speed", "star", "shield")

def has_sword(snake):
    return snake_has_keyword(snake, "sword")

def has_stack(snake):
    return snake_has_keyword(snake, "stack")

# ==========================================================
# STAR / BOOST / SWORD RULE FLAGS (PLACEHOLDERS)
# ==========================================================

def star_active(snake):
    return snake_has_keyword(snake, "star", "shield")

def boost_active(snake):
    return snake_has_keyword(snake, "boost")

# ==========================================================
# SAFE CELL CHECK (LIGHT VERSION - NO COMBAT YET)
# ==========================================================

def is_safe_cell(pos, blocked, enemy_heads, size):
    """
    STRICT RULE:
    - immediate head collision = ALWAYS unsafe
    """
    if pos in blocked:
        return False

    w, h = size
    for hpos in enemy_heads:
        if wrap_dist(pos, hpos, w, h) <= 1:
            return False

    return True


# ==========================================================
# ENEMY INTELLIGENCE MODULE
# ==========================================================

def build_enemy_maps(my_head, snakes, size):
    """
    Builds global threat zones for all enemies.
    STRICT RULE INCLUDED:
    - head-to-head is absolute death zone
    """
    w, h = size

    enemy_heads = []
    enemy_bodies = set()

    danger_1 = set()
    danger_2 = set()
    danger_3 = set()

    sword_threat = set()
    boost_threat = set()
    star_threat = set()

    head_kill_zone = set()

    for s in snakes:
        head = s.get("head")
        body = list(s.get("body", []))

        if not body:
            continue

        if head == my_head:
            continue

        enemy_heads.append(head)
        enemy_bodies.update(body)

        # ==================================================
        # HEAD KILL ZONE (ABSOLUTE RULE)
        # ==================================================
        head_kill_zone.add(head)

        for n in neighbors(head, w, h):
            danger_1.add(n)

        # 2-step and 3-step expansion
        frontier = set(neighbors(head, w, h))
        for p in frontier:
            danger_2.add(p)

        next_frontier = set()
        for p in frontier:
            for n in neighbors(p, w, h):
                next_frontier.add(n)
        danger_3.update(next_frontier)

        # ==================================================
        # SWORD / BOOST / STAR PREDICTIONS
        # ==================================================

        speed = snake_has_keyword(s, "speed", "boost")
        sword = snake_has_keyword(s, "sword")
        star = snake_has_keyword(s, "star", "shield")

        # BOOST: 2-cell reach approximation
        if speed:
            for n1 in neighbors(head, w, h):
                boost_threat.add(n1)
                for n2 in neighbors(n1, w, h):
                    boost_threat.add(n2)

        # SWORD: cuts adjacent body + extended pressure
        if sword:
            for b in body:
                sword_threat.add(b)
                for n in neighbors(b, w, h):
                    sword_threat.add(n)

        # STAR: enemy can pass through EVERYTHING except heads
        # So only heads matter; body becomes moving hazard
        if star:
            for b in body:
                star_threat.add(b)

    return {
        "enemy_heads": enemy_heads,
        "enemy_bodies": enemy_bodies,

        "danger_1": danger_1,
        "danger_2": danger_2,
        "danger_3": danger_3,

        "sword_threat": sword_threat,
        "boost_threat": boost_threat,
        "star_threat": star_threat,

        "head_kill_zone": head_kill_zone,
    }

# ==========================================================
# BODY EXPOSURE MODEL
# ==========================================================

def body_exposure_score(my_body, enemy_maps):
    """
    Measures how punishable your body is.
    Higher = you are about to get cut or boosted into.
    """
    if not my_body:
        return 0

    exposure = 0
    body_set = set(my_body)

    exposure += 1000 * len(body_set & enemy_maps["sword_threat"])
    exposure += 600 * len(body_set & enemy_maps["boost_threat"])
    exposure += 350 * len(body_set & enemy_maps["danger_1"])
    exposure += 150 * len(body_set & enemy_maps["danger_2"])
    exposure += 120 * len(body_set & enemy_maps["star_threat"])

    return exposure

# ==========================================================
# GLOBAL SAFETY FILTER (CRITICAL)
# ==========================================================

def is_illegal_head_move(pos, enemy_maps):
    """
    ABSOLUTE RULE:
    - NEVER enter enemy head cell (even mutual death is forbidden)
    """
    return pos in enemy_maps["head_kill_zone"]

def is_immediate_death(pos, enemy_maps):
    """
    Hard kill zones:
    """
    return (
        pos in enemy_maps["danger_1"] or
        pos in enemy_maps["head_kill_zone"]
    )

# ==========================================================
# RISK SCORING ENGINE
# ==========================================================

def cell_risk_score(pos, enemy_maps):
    risk = 0

    if pos in enemy_maps["danger_1"]:
        risk += 900
    if pos in enemy_maps["danger_2"]:
        risk += 350
    if pos in enemy_maps["danger_3"]:
        risk += 120

    if pos in enemy_maps["sword_threat"]:
        risk += 800

    if pos in enemy_maps["boost_threat"]:
        risk += 500

    if pos in enemy_maps["star_threat"]:
        risk += 250

    if pos in enemy_maps["head_kill_zone"]:
        risk += 10_000  # absolute forbidden

    return risk

# ==========================================================
# SAFE MOVE FILTER
# ==========================================================

def filter_safe_moves(moves_dict, enemy_maps, blocked):
    """
    Removes illegal head-to-head moves + hard danger cells
    """
    safe = {}

    for m, pos in moves_dict.items():

        if pos in blocked:
            continue

        if is_illegal_head_move(pos, enemy_maps):
            continue

        if pos in enemy_maps["danger_1"]:
            continue

        safe[m] = pos

    return safe

# ==========================================================
# CONTEXT CONTEST CHECK
# ==========================================================

def is_contested(pos, my_head, snakes, size):
    w, h = size
    my_d = wrap_dist(my_head, pos, w, h)

    for s in snakes:
        if s.get("head") == my_head:
            continue
        if wrap_dist(s["head"], pos, w, h) <= my_d:
            return True

    return False

# ==========================================================
# LOOKAHEAD ESCAPE VALIDATION
# ==========================================================

def has_escape(nxt, blocked, size):
    """
    Ensures next cell is not a dead-end trap
    """
    w, h = size

    escape = 0
    for d in DIRECTIONS.values():
        nn = wrap(add(nxt, d), w, h)
        if nn not in blocked:
            escape += 1

    return escape > 0

# ==========================================================
# ITEM + COMBAT EXECUTION MODULE
# ==========================================================

# ==========================================================
# TARGET SELECTION (IMPROVED)
# ==========================================================

def choose_best_target(my_head, targets, enemy_maps, size):
    """
    Picks safest + closest + least contested target
    """
    if not targets:
        return None

    w, h = size

    ranked = sorted(
        targets,
        key=lambda t: (
            wrap_dist(my_head, t, w, h),
            cell_risk_score(t, enemy_maps)
        )
    )

    return ranked[0]

# ==========================================================
# STAR MODE STRATEGY (OFFENSIVE + EXIT)
# ==========================================================

def star_strategy(my_head, my_body, enemy_maps, blocked, size):
    """
    STAR MODE:
    - ignore bodies and obstacles
    - ONLY avoid enemy heads
    - maximize body cutting
    - prepare exit BEFORE expiry
    """

    w, h = size

    # Find densest enemy body region
    body_cells = list(enemy_maps["enemy_bodies"])

    if not body_cells:
        return None

    # cluster heuristic: pick cell near many body segments
    def score(t):
        return sum(1 for b in body_cells if wrap_dist(t, b, w, h) <= 2)

    best_target = max(body_cells, key=score)

    # direct greedy step toward it (no BFS needed in star mode)
    best_move = None
    best_dist = 10**9

    for m, d in DIRECTIONS.items():
        nxt = wrap(add(my_head, d), w, h)

        # ONLY enemy head is forbidden in star mode
        if is_illegal_head_move(nxt, enemy_maps):
            continue

        dist = wrap_dist(nxt, best_target, w, h)

        if dist < best_dist:
            best_dist = dist
            best_move = m

    return best_move

# ==========================================================
# BOOST VALIDATION (2-CELL SAFETY FIX)
# ==========================================================

def validate_boost_path(my_head, move, enemy_maps, blocked, size):
    """
    Boost moves 2 cells:
    MUST validate both intermediate and final cell
    """

    w, h = size

    delta = DIRECTIONS[move]
    step1 = wrap(add(my_head, delta), w, h)
    step2 = wrap(add(step1, delta), w, h)

    if step1 in blocked or step2 in blocked:
        return False

    if is_illegal_head_move(step1, enemy_maps):
        return False

    if is_illegal_head_move(step2, enemy_maps):
        return False

    if step1 in enemy_maps["danger_1"]:
        return False

    return True

# ==========================================================
# SWORD TIMING (EXACT HIT LOGIC)
# ==========================================================

def sword_should_activate(my_head, snakes, enemy_maps):
    """
    Activate ONLY if sword will hit THIS TURN
    """

    for s in snakes:
        if s.get("head") == my_head:
            continue

        body = list(s.get("body", []))

        # immediate adjacency cut
        for b in body[1:]:
            if wrap_dist(my_head, b, 1, 10**9) == 1:
                return True

    return False

# ==========================================================
# STACK PANIC CONDITION
# ==========================================================

def should_stack(my_body, enemy_maps, exposure_threshold=1200):
    """
    Stack is PURE defense:
    - body heavily exposed
    - multiple threats overlap
    """

    if not my_body:
        return False

    exposure = body_exposure_score(my_body, enemy_maps)

    if exposure >= exposure_threshold:
        return True

    # surrounded check
    if len(set(my_body) & enemy_maps["danger_1"]) > 0:
        return True

    return False

# ==========================================================
# SAFE ITEM FILTER
# ==========================================================

def filter_safe_items(items, enemy_maps, my_head, size):
    """
    removes suicidal items (trap apples, contested death zones)
    """

    safe = []
    w, h = size

    for it in items:
        pos = it

        if pos in enemy_maps["danger_1"]:
            continue

        if is_illegal_head_move(pos, enemy_maps):
            continue

        if wrap_dist(my_head, pos, w, h) <= 1:
            continue

        safe.append(pos)

    return safe

# ==========================================================
# CONTEXTUAL ITEM PRIORITY
# ==========================================================

def item_priority(my_head, apples, swords, stacks, boosts, stars, enemy_maps, size):
    """
    Decides WHAT matters right now
    """

    exposure = len(enemy_maps["danger_1"])

    # STAR overrides everything
    if stars:
        return "STAR"

    # emergency survival
    if exposure > 15:
        return "STACK"

    # offensive opportunity
    if swords:
        return "SWORD"

    # mobility
    if boosts:
        return "BOOST"

    # survival food
    if apples:
        return "APPLE"

    return None

# ==========================================================
# MAIN DECISION HOOK (LOGIC OUTPUT ONLY)
# ==========================================================

def decide_action(my_head, snakes, items, enemy_maps, size):
    """
    returns:
    - target mode
    - item action suggestion
    """

    my_snake = next((s for s in snakes if s.get("head") == my_head), None)
    my_body = my_snake.get("body", []) if my_snake else []

    apples, bad, swords, boosts, stars, speeds, stacks = classify_items(items)

    priority = item_priority(
        my_head,
        apples, swords, stacks, boosts, stars,
        enemy_maps,
        size
    )

    action = {
        "mode": None,
        "target": None
    }

    # ==================================================
    # STAR MODE
    # ==================================================
    if priority == "STAR":
        action["mode"] = "STAR"
        action["target"] = star_strategy(
            my_head, my_body, enemy_maps,
            blocked=set(), size=size
        )
        return action

    # ==================================================
    # STACK MODE
    # ==================================================
    if priority == "STACK" and should_stack(my_body, enemy_maps):
        action["mode"] = "STACK"
        return action

    # ==================================================
    # SWORD MODE
    # ==================================================
    if priority == "SWORD":
        action["mode"] = "SWORD"
        return action

    # ==================================================
    # BOOST MODE
    # ==================================================
    if priority == "BOOST":
        action["mode"] = "BOOST"
        return action

    # ==================================================
    # APPLE MODE (SAFE CHASE)
    # ==================================================
    safe_apples = filter_safe_items(apples, enemy_maps, my_head, size)
    action["mode"] = "APPLE"
    action["target"] = choose_best_target(my_head, safe_apples, enemy_maps, size)

    return action

# ==========================================================
# FINAL CONTROLLER / MOVE ENGINE
# ==========================================================

_last_tick = 0
_last_boost = -100
_last_sword = -100
_last_stack = -100

# ==========================================================
# MOVE SIMULATION
# ==========================================================

def simulate_move(my_head, move, size):
    return wrap(add(my_head, DIRECTIONS[move]), *size)

# ==========================================================
# MAIN DECISION FUNCTION
# ==========================================================

def choose_next_move(my_head, obstacles, snakes, size, items, direction):
    global _tick, _last_boost, _last_sword, _last_stack

    _ensure_state()   # 👈 ADD THIS LINE FIRST

    _tick += 1
    w, h = size
    my_snake = next((s for s in snakes if s.get("head") == my_head), None)
    my_body = my_snake.get("body", []) if my_snake else []
    inventory = my_snake.get("inventory", []) if my_snake else []

    my_body_set = set(my_body)
    my_body_no_head = set(my_body[1:])

    apples, bad, swords, boosts, stars, speeds, stacks = classify_items(items)

    # ==========================================================
    # BUILD ENEMY INTELLIGENCE
    # ==========================================================
    enemy_maps = build_enemy_maps(my_head, snakes, size)

    blocked = set(obstacles) | my_body_no_head | enemy_maps["enemy_bodies"]

    enemy_heads = enemy_maps["enemy_heads"]

    # ==========================================================
    # ACTION DECISION
    # ==========================================================
    action = decide_action(my_head, snakes, items, enemy_maps, size)

    # STAR MODE OVERRIDE
    if action["mode"] == "STAR":
        move = action["target"]
        return move, "STAR"

    # ==========================================================
    # GENERATE LEGAL MOVES
    # ==========================================================
    moves = {}

    for m, d in DIRECTIONS.items():

        if m == OPPOSITE.get(direction):
            continue

        nxt = simulate_move(my_head, m, size)

        if nxt in blocked:
            continue

        if is_illegal_head_move(nxt, enemy_maps):
            continue

        moves[m] = nxt

    if not moves:
        return direction, None

    # ==========================================================
    # MOVE SCORING
    # ==========================================================

    best_move = direction
    best_score = -10**18

    for m, pos in moves.items():

        score = 0

        # --------------------------
        # SURVIVAL SPACE
        # --------------------------
        space = flood_fill(pos, blocked, size)
        score += space * 12

        if is_trapped(pos, blocked, size):
            score -= 800

        # --------------------------
        # ESCAPE OPTIONS
        # --------------------------
        score += escape_options(pos, blocked, size) * 40

        # --------------------------
        # ENEMY PRESSURE
        # --------------------------
        score -= cell_risk_score(pos, enemy_maps)

        # --------------------------
        # BODY EXPOSURE
        # --------------------------
        future_body = [pos] + my_body[:-1]
        score -= body_exposure_score(future_body, enemy_maps) * 0.4

        # --------------------------
        # APPLES
        # --------------------------
        if pos in apples:
            score += 250

        if pos in bad:
            score -= 400

        nd = nearest_distance(pos, apples, size)
        if nd is not None:
            score += 120 / (nd + 1)

        # --------------------------
        # VALUABLE ITEMS
        # --------------------------
        if pos in swords:
            score += 300
        if pos in stacks:
            score += 280
        if pos in boosts:
            score += 200
        if pos in stars:
            score += 350

        # --------------------------
        # CONTINUITY BONUS
        # --------------------------
        if m == direction:
            score += 15

        # --------------------------
        # ENEMY HEAD PROXIMITY PENALTY (CRITICAL)
        # --------------------------
        for hpos in enemy_heads:
            d = wrap_dist(pos, hpos, w, h)

            if d <= 1:
                score -= 2000
            elif d == 2:
                score -= 500
            elif d <= 4:
                score -= 120

        # --------------------------
        # STAR EXIT SAFETY (IMPORTANT)
        # --------------------------
        if action["mode"] == "STAR":
            if is_trapped(pos, blocked, size):
                score -= 1500

        # --------------------------
        # BOOST SAFETY CHECK
        # --------------------------
        if action["mode"] == "BOOST":
            nxt2 = wrap(add(pos, DIRECTIONS[m]), w, h)
            if nxt2 in blocked:
                score -= 1000

        if score > best_score:
            best_score = score
            best_move = m

    final_pos = simulate_move(my_head, best_move, size)

    # ==========================================================
    # FINAL ITEM ACTIVATION
    # ==========================================================

    activate = None

    # --------------------------
    # STACK (panic defense)
    # --------------------------
    if has_stack(inventory):
        exposure = body_exposure_score(my_body, enemy_maps)

        if exposure > 1200 and _tick - _last_stack > 5:
            activate = "STACK"
            _last_stack = _tick

    # --------------------------
    # BOOST (escape / chase)
    # --------------------------
    if activate is None and boost_active(my_snake):
        if cell_risk_score(final_pos, enemy_maps) > 500:
            activate = "BOOST"
            _last_boost = _tick

    # --------------------------
    # SWORD (ONLY ON HIT)
    # --------------------------
    if activate is None and has_sword(my_snake):
        if sword_should_activate(my_head, snakes, enemy_maps):
            activate = "SWORD"
            _last_sword = _tick

    return best_move, activate