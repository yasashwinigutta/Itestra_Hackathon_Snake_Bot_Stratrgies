# Itestra Hackathon Snake Bot Strategies

🥇 **1st Place Winner – Itestra Snake Bot Hackathon**

This repository documents my individual strategy development throughout the Itestra Snake Bot Hackathon.

The game rules changed repeatedly across rounds, introducing:

- Positive apples
- Bad apples
- Center-diamond apple layouts
- Star boosts
- Sword combat
- Boost / speed movement
- Stack-based emergency escape
- Wrap-around maps
- Multi-agent free-for-all environments

The challenge was to continuously redesign the bot strategy while preserving compatibility with the shared game framework.

---

## Repository Structure

The project followed a modular architecture.

### Shared Framework

These files provided the common interface to the game:

- `api.py`
- `data_structures.py`
- `Field.py`
- `main.py`
- `main2.py`
- `main3.py`
- `main_final.py`

Most of the game framework was shared across the team.

---

## My Main Contributions

My primary contributions were in **strategy development**.

I designed, implemented and iteratively improved multiple strategy files as the game rules evolved.

### Center Apple Strategies

Files:

- `center_apple_strategy_ffa.py`
- `center_apple_strategy_ffa_2.py`
- `center_apple_strategy_ffa_3.py`

Focus:

- Rush center diamond apples
- Early-game score maximization
- Safe transition to global apple collection

---

### Bad Apple Endurance Strategies

Files:

- `bad_apple_endurance_strategy.py`
- `bad_apple_endurance_strategy_2.py`
- `bad_apple_endurance_strategy_3.py`

Focus:

- Survival-first movement
- Risk-aware bad apple handling
- Flood-fill based open-space scoring

---

### Star Control Strategies

Files:

- `star_control_strategy_2.py`
- `star_control_strategy_3.py`
- `star_control_strategy_4.py`
- `star_control_strategy_5.py`
- `star_control_strategy_6.py`

Focus:

- Star race evaluation
- Wrap-around shortest paths
- Contested star avoidance
- Post-star scoring strategies

---

### Stack Safe Combat Strategies

Files:

- `stack_safe_strategy.py`
- `stack_safe_strategy_2.py`
- `stack_safe_strategy_3.py`
- `stack_safe_strategy_4.py`
- `stack_safe_strategy_5.py`

Focus:

- Emergency Stack activation
- Sword threat avoidance
- Body exposure estimation
- Enemy prediction

---

### All-Items Strategies

Files:

- `strategy_all_items_at_once_1.py`
- `strategy_all_items_at_once_2.py`
- `strategy_all_items_at_once_3.py`

Focus:

Integrating:

- Apples
- Bad apples
- Star
- Sword
- Boost
- Speed
- Stack

into a unified decision-making strategy.

---

### Final Hybrid Strategies

Files:

- `strategy_final.py`
- `strategy_final2.py`
- `strategy_final3.py`

Focus:

- Enemy prediction (1–3 step lookahead)
- Dead snake body avoidance
- Open-space scoring
- Combat vs survival tradeoffs
- Risk-aware pathfinding
- Dynamic item prioritization
- Multi-agent free-for-all optimization

---

## Additional Contributions

Although strategy development was my primary contribution, I also contributed to modifications of:

- `main.py`
- `main2.py`
- `main3.py`
- `main_final.py`

whenever item handling or strategy integration required framework-level changes.

---

## Final Team Repository

The final structured team repository is available here:

**[https://github.com/VishnucharanS/Itestra_Hackathon]**

This repository contains the final structured implementation developed collaboratively during the hackathon and submitted as the team's official solution.

---

## About This Repository

The purpose of Itestra_Hackathon_Snake_Bot_Stratrgies is different from the final team repository.

This repository serves as a personal record of my individual contributions and strategy development throughout the competition. It documents the evolution of the bot across multiple rounds, changing game rules, and progressively more complex environments.

The strategies presented here include:

Center-diamond apple collection strategies
Bad-apple endurance strategies
Star-control strategies
Sword and boost combat strategies
Stack-safe survival strategies
All-items integration strategies
Final hybrid combat-control survival strategies

Most of my work focused on designing and iteratively improving the strategy modules, while maintaining compatibility with the shared game framework (api.py, Field.py, data_structures.py, and various main files).

Several ideas and strategy components developed here were later adapted and integrated into the final team submission.

For the final polished implementation and complete project structure, please refer to the official team repository above.

🥇 **Outcome:**  
The team secured **1st Place** in the Itestra Snake Bot Hackathon.
