import heapq


# ======== TUNABLE WEIGHTS ========
POWERED_KILL_REWARD = 1400
SAFE_STAR_REWARD = 520
ADJACENT_GOOD_APPLE_REWARD = 260
GOOD_APPLE_REWARD = 95
OPEN_SPACE_WEIGHT = 3.8
BAD_APPLE_PENALTY = 70
CONTESTED_STAR_PENALTY = 260
ENEMY_HEAD_RISK_PENALTY = 120
OWN_BODY_COLLISION_PENALTY = 500
BOOST_END_SAFETY_MARGIN = 2


# ======== UTILITIES ========
def dist(a, b, w, h):
    return min(abs(a[0] - b[0]), w - abs(a[0] - b[0])) + \
           min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))


def neighbors(p, w, h):
    x, y = p
    return [
        ((x + 1) % w, y),
        ((x - 1) % w, y),
        (x, (y + 1) % h),
        (x, (y - 1) % h),
    ]


def item_position(item):
    if hasattr(item, "position"):
        return tuple(item.position)
    if isinstance(item, dict):
        pos = item.get("position")
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            return tuple(pos[:2])
    if isinstance(item, (list, tuple)) and len(item) >= 1:
        pos = item[0]
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            return tuple(pos[:2])
    return None


def item_kind(item):
    if hasattr(item, "kind"):
        return item.kind
    if isinstance(item, dict):
        return item.get("kind")
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        return item[1]
    return None


def snake_has_power(snake):
    if not snake:
        return False
    for effect in snake.get("active_effects", []):
        if isinstance(effect, dict):
            name = str(effect.get("effect", "")).lower()
        else:
            name = str(effect).lower()
        if "star" in name or "powered" in name or "boost" in name:
            return True
    return False


def power_remaining(snake):
    if not snake:
        return 0
    remaining = 0
    for effect in snake.get("active_effects", []):
        if isinstance(effect, dict):
            try:
                remaining = max(remaining, int(effect.get("remaining_ticks", 0)))
            except Exception:
                pass
    return remaining


def classify_items(items):
    good_apples = []
    bad_apples = []
    stars = []
    for item in items:
        pos = item_position(item)
        if pos is None:
            continue
        kind = item_kind(item)
        if isinstance(kind, str) and kind.lower().startswith("star"):
            stars.append(pos)
            continue
        if isinstance(kind, str) and kind.lower().startswith("apple"):
            if "bad" in kind.lower():
                bad_apples.append(pos)
            else:
                good_apples.append(pos)
            continue
        if kind == "Apple":
            good_apples.append(pos)
        elif kind == "BadApple":
            bad_apples.append(pos)
    return good_apples, bad_apples, stars


def shortest_path(start, goal, blocked, bad_positions, w, h, allow_bad=True):
    pq = [(0, 0, start)]
    best = {start: (0, 0)}
    prev = {start: None}

    while pq:
        dist_so_far, bad_so_far, pos = heapq.heappop(pq)
        if best.get(pos, (1e9, 1e9)) < (dist_so_far, bad_so_far):
            continue
        if pos == goal:
            path = []
            cur = pos
            while cur is not None:
                path.append(cur)
                cur = prev[cur]
            path.reverse()
            first_step = path[1] if len(path) > 1 else path[0]
            return dist_so_far, bad_so_far, first_step, path

        for nxt in neighbors(pos, w, h):
            if nxt in blocked:
                continue
            if not allow_bad and nxt in bad_positions:
                continue
            next_bad = bad_so_far + (1 if nxt in bad_positions else 0)
            state = (dist_so_far + 1, next_bad)
            if nxt not in best or state < best[nxt]:
                best[nxt] = state
                prev[nxt] = pos
                heapq.heappush(pq, (state[0], state[1], nxt))

    return None, None, None, None


def reachable_space(start, blocked, w, h, limit=500):
    seen = {start}
    queue = [start]
    count = 0
    while queue and count < limit:
        current = queue.pop(0)
        count += 1
        for nxt in neighbors(current, w, h):
            if nxt in seen or nxt in blocked:
                continue
            seen.add(nxt)
            queue.append(nxt)
    return count


def enemy_danger_zones(snakes, w, h, my_head=None, steps=3):
    danger = set()
    for s in snakes:
        head = s["head"]
        if my_head is not None and head == my_head:
            continue
        body = set(s.get("body", []))
        forbidden = s["body"][1] if len(s.get("body", [])) >= 2 else None
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


def enemy_targets(snakes, my_head):
    targets = []
    for s in snakes:
        if s["head"] == my_head:
            continue
        body = s.get("body", [])
        for idx, cell in enumerate(body):
            targets.append({
                "pos": cell,
                "type": "head" if idx == 0 else "body",
                "length": len(body),
            })
    return targets


def immediate_adjacent_positions(pos, w, h):
    return neighbors(pos, w, h)


def find_powered_attack_move(my_head, own_body, enemy_targets, moves, w, h, remaining_boost):
    enemy_positions = {t["pos"] for t in enemy_targets}
    # Immediate kill in 1 move
    for move, pos in moves.items():
        if pos in enemy_positions and pos not in own_body:
            return move

    best = None
    best_score = -1e18
    for move, pos in moves.items():
        if pos in own_body:
            continue
        score = 0
        for target in enemy_targets:
            d = dist(pos, target["pos"], w, h)
            if d <= 1:
                score += POWERED_KILL_REWARD
                if target["type"] == "head":
                    score += 260
                score += target["length"] * 12
            elif d == 2:
                score += POWERED_KILL_REWARD * 0.5
                if target["type"] == "head":
                    score += 120
                score += target["length"] * 7
            score -= d * 20
        score += reachable_space(pos, own_body, w, h) * 1.8
        if remaining_boost <= BOOST_END_SAFETY_MARGIN:
            score += escape_score(pos, own_body, w, h) * 8
            score -= 140
        if score > best_score:
            best_score = score
            best = move
    return best


def escape_score(pos, blocked, w, h):
    return sum(1 for nxt in neighbors(pos, w, h) if nxt not in blocked)


def find_best_star_move(my_head, own_body, enemy_body, enemy_heads, stars, bad_positions, obstacles, w, h):
    best = None
    best_score = -1e18
    best_star_metrics = None
    blocked = own_body | enemy_body
    for star in stars:
        my_len, my_bad, my_step, my_path = shortest_path(
            my_head,
            star,
            blocked,
            bad_positions,
            w,
            h,
            allow_bad=True,
        )
        if my_len is None:
            continue

        enemy_min = 1e9
        for head in enemy_heads:
            enemy_len, _, _, _ = shortest_path(
                head,
                star,
                blocked,
                bad_positions,
                w,
                h,
                allow_bad=True,
            )
            if enemy_len is not None:
                enemy_min = min(enemy_min, enemy_len)

        if enemy_min == 1e9:
            continue
        if my_len >= enemy_min:
            continue

        open_space = reachable_space(star, obstacles, w, h)
        score = SAFE_STAR_REWARD - my_len * 26 - my_bad * 18 + open_space * 2
        if score > best_score or (score == best_score and open_space > best_star_metrics["open_space"]):
            best_score = score
            best = my_step
            best_star_metrics = {"open_space": open_space}
    return best


def adjacent_good_apple_move(my_head, good_apples, moves, obstacles, w, h):
    targets = set(good_apples)
    for move, pos in moves.items():
        if any(dist(pos, apple, w, h) == 1 for apple in targets) and pos not in obstacles:
            return move
    return None


def score_normal_move(pos, move, good_apples, bad_positions, enemy_zones, star_positions, obstacles, w, h):
    score = 0
    score += reachable_space(pos, obstacles, w, h) * OPEN_SPACE_WEIGHT
    score += escape_score(pos, obstacles, w, h) * 8
    if pos in bad_positions:
        score -= BAD_APPLE_PENALTY
    if pos in enemy_zones:
        score -= ENEMY_HEAD_RISK_PENALTY
    if good_apples:
        nearest = min(dist(pos, apple, w, h) for apple in good_apples)
        score += GOOD_APPLE_REWARD / (nearest + 1)
        if any(dist(pos, apple, w, h) == 1 for apple in good_apples):
            score += ADJACENT_GOOD_APPLE_REWARD
    if star_positions:
        nearest_star = min(dist(pos, star, w, h) for star in star_positions)
        score -= CONTESTED_STAR_PENALTY / (nearest_star + 1)
    return score


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

    my_snake = next((s for s in snakes if s["head"] == my_head), None)
    own_body = set(my_snake.get("body", [])) if my_snake else set()
    enemy_bodies = set()
    enemy_heads = []
    for s in snakes:
        if s["head"] == my_head:
            continue
        enemy_heads.append(s["head"])
        enemy_bodies.update(s.get("body", []))

    safe_moves = {
        d: p for d, p in moves.items()
        if d != forbidden and p not in obstacles
    }
    if not safe_moves:
        return current_direction

    good_apples, bad_apples, stars = classify_items(items)
    bad_positions = set(bad_apples)
    enemy_zones = enemy_danger_zones(snakes, w, h, my_head=my_head, steps=3)

    powered = snake_has_power(my_snake)
    remaining_boost = power_remaining(my_snake)

    if powered:
        powered_moves = {
            d: p for d, p in moves.items()
            if d != forbidden and p not in own_body
        }
        targets = enemy_targets(snakes, my_head)
        kill_move = find_powered_attack_move(my_head, own_body, targets, powered_moves, w, h, remaining_boost)
        if kill_move:
            return kill_move

    if not powered and stars:
        star_move = find_best_star_move(
            my_head,
            own_body,
            enemy_bodies,
            enemy_heads,
            stars,
            bad_positions,
            obstacles,
            w,
            h,
        )
        if star_move:
            return star_move

    if not powered and good_apples:
        adjacent_move = adjacent_good_apple_move(my_head, good_apples, safe_moves, obstacles, w, h)
        if adjacent_move:
            return adjacent_move

    best_move = None
    best_score = -1e18
    for move, pos in safe_moves.items():
        score = score_normal_move(
            pos,
            move,
            good_apples,
            bad_positions,
            enemy_zones,
            stars,
            obstacles,
            w,
            h,
        )
        if score > best_score:
            best_score = score
            best_move = move

    return best_move
