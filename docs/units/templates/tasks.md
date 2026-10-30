# <unit> — tasks

Fork branch `unit/<unit>` from `rzv2l-dev` `<sha>`; project branch of the same name from `main` `<sha>`.

| ID | Task | Fork commit | Test | Status |
|---|---|---|---|---|
| T1 | … | `<sha>` | qtest `/…` | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `<function>`: <the change> | `<test>.c:<line> <test>`: `<got> == <want>` |

Each mutation is built with a confirmed relink and run alone; the model is restored and rebuilt, and the full test passes after each.

## Boot evidence (<date>, fork `<sha>`)
The command, and the guest lines that show the exit criterion.
