import argparse
import time

from api import SnakeFieldAPI
import strategy_final as strategy


# ==========================================================
# VALIDATION
# ==========================================================

def is_valid_coord(c):
    return isinstance(c, (list, tuple)) and len(c) >= 2


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("team_name")
    parser.add_argument("game_name")
    parser.add_argument("--password", default="test")
    parser.add_argument("--base_url", default="http://localhost:3030")

    args = parser.parse_args()

    api = SnakeFieldAPI(
        args.base_url,
        args.team_name,
        args.game_name,
        args.password
    )

    current_direction = "NORTH"
    api.set_direction(current_direction)

    print("Bot started.")

    tick = 0

    # ==========================================================
    # GAME LOOP
    # ==========================================================
    while True:
        time.sleep(0.5)
        tick += 1

        field = api.get_field()
        if not field:
            continue

        snake = field.snakes.get(args.team_name)
        if not snake or not snake.alive or not snake.body:
            continue

        head = snake.body[0]

        if not is_valid_coord(head):
            continue

        my_head = (int(head[0]), int(head[1]))

        # ==========================================================
        # OBSTACLES + SNAKE INFO
        # ==========================================================
        obstacles = set()
        snakes_info = []

        for name, s in field.snakes.items():
            body = [(int(x), int(y)) for x, y in s.body]

            if not body:
                continue

            obstacles.update(body)

            snakes_info.append({
                "name": name,
                "body": body,
                "head": body[0],
                "inventory": list(getattr(s, "inventory", [])) if getattr(s, "inventory", None) else [],
                "body_no_head": body[1:] if len(body) > 1 else []
            })

        # ==========================================================
        # ITEMS
        # ==========================================================
        items = field.items

        print(
            f"[DBG] tick={tick} "
            f"A:{sum('apple' in str(i.kind).lower() for i in items)} "
            f"B:{sum('bad' in str(i.kind).lower() for i in items)} "
            f"S:{sum('sword' in str(i.kind).lower() for i in items)} "
            f"Z:{sum('boost' in str(i.kind).lower() for i in items)}"
        )

        # ==========================================================
        # STRATEGY CALL
        # ==========================================================
        try:
            result = strategy.choose_next_move(
                my_head,
                obstacles,
                snakes_info,
                field.size,
                items,
                current_direction,
            )
        except Exception as e:
            print(f"[STRATEGY ERROR] {e}")
            continue

        # ==========================================================
        # NORMALIZE STRATEGY OUTPUT
        # ==========================================================
        activate = None
        new_dir = current_direction

        if isinstance(result, tuple):
            if len(result) == 2:
                new_dir, activate = result
            elif len(result) == 1:
                new_dir = result[0]
        else:
            new_dir = result

        # ==========================================================
        # ITEM ACTIVATION HANDLER
        # ==========================================================
        if isinstance(activate, str):

            # ---------------- SWORD ----------------
            if activate.upper() == "SWORD":
                item_name = next(
                    (inv for inv in snake.inventory if "sword" in str(inv).lower()),
                    None
                )

                if item_name:
                    resp = api.activate_item(item_name)
                    if resp and resp.status_code == 200:
                        try:
                            snake.inventory.remove(item_name)
                        except Exception:
                            pass

            # ---------------- BOOST ----------------
            elif activate.upper() == "BOOST":
                item_name = next(
                    (inv for inv in snake.inventory if "boost" in str(inv).lower()),
                    None
                )

                if item_name:
                    resp = api.activate_item(item_name)
                    if resp and resp.status_code == 200:
                        try:
                            snake.inventory.remove(item_name)
                        except Exception:
                            pass

            # ---------------- STACK / STAR (if API supports direct trigger) ----------------
            elif activate.upper() in ["STACK", "STAR"]:
                item_name = next(
                    (inv for inv in snake.inventory if activate.lower() in str(inv).lower()),
                    None
                )

                if item_name:
                    api.activate_item(item_name)

        # ==========================================================
        # UPDATE DIRECTION
        # ==========================================================
        current_direction = new_dir
        api.set_direction(current_direction)