import argparse
import time

from api import SnakeFieldAPI
from strategyfight1 import choose_next_move

def is_valid_coord(c):
    return isinstance(c, (list, tuple)) and len(c) >= 2


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

        # ---------------- OBSTACLES ----------------
        obstacles = set()
        snakes_info = []

        for name, s in field.snakes.items():
            body = [(int(x), int(y)) for x, y in s.body]

            obstacles.update(body)

            snakes_info.append({
                "name": name,
                "body": body,
                "head": body[0],
                "inventory": list(s.inventory) if getattr(s, "inventory", None) is not None else [],
                # convenience: provide body without head for callers that prefer it
                "body_no_head": body[1:] if len(body) > 1 else []
            })

        # ---------------- ITEMS ----------------
        items = field.items

        print(
            f"[DBG] tick={tick} "
            f"A:{sum('apple' in str(i.kind).lower() for i in items)} "
            f"B:{sum('bad' in str(i.kind).lower() for i in items)} "
            f"S:{sum('sword' in str(i.kind).lower() for i in items)} "
            f"Z:{sum('boost' in str(i.kind).lower() for i in items)}"
        )

        # ---------------- STRATEGY ----------------
        new_dir, activate = choose_next_move(
            my_head,
            obstacles,
            snakes_info,
            field.size,
            items,
            current_direction,
        )

        # ---------------- SAFE ACTION HANDLER ----------------
        if isinstance(activate, str):
            # prefer activating the exact inventory token from the snake data
            if activate.upper() == "SWORD":
                item_name = next((inv for inv in snake.inventory if "sword" in str(inv).lower()), None)
                item_to_send = item_name or "Sword"
                resp = api.activate_item(item_to_send)
                if resp is not None and resp.status_code == 200:
                    try:
                        snake.inventory.remove(item_name)
                    except Exception:
                        pass

            elif activate.upper() == "BOOST":
                item_name = next((inv for inv in snake.inventory if "boost" in str(inv).lower()), None)
                item_to_send = item_name or "Speed Boost"
                resp = api.activate_item(item_to_send)
                if resp is not None and resp.status_code == 200:
                    try:
                        snake.inventory.remove(item_name)
                    except Exception:
                        pass

        elif activate is True:
            # fallback compatibility (old strategies)
            print("[DEBUG] GENERIC ITEM USED")
            api.activate_item("Speed Boost")

        # ---------------- MOVE UPDATE ----------------
        current_direction = new_dir
        api.set_direction(current_direction)