"""The Builder (BUILDER.md, ADR-050 proposed): Kairu builds things, writes its own skills, and tries a big task five ways.

    make.py     Builder powers: a website, a web app, slides, or a small Python program with its tests, written by the free
                cloud AI (Gemini first, brain.build_providers) from a public brief, read strictly, shown, then made in a NEW
                folder in your work folder (build.write, Medium); its tests run only with "yes" and your PIN (build.test, High)
    forge.py    Forge: an order no skill fits becomes a recipe of KNOWN orders; every step gets its tier from Guardian (Critical
                means no skill), the recipe runs five times on a stand-in laptop (forge.test), and it is kept only with "yes"
                and your PIN (forge.save, High). From then on it is a known order: shown first, and Guardian decides each step
    paths.py    Five Paths: five plans for one big task (Fast, Careful, Simple, Creative, Thorough), the rule checks drop any
                with a refused or Critical step, a judge scores the rest against "done when", and you pick; only that one runs
    conduct.py  the task core's side: the orders above, and the order in which Guardian is asked
    store.py    data/builder.db, on this PC only: drafts, recipes, kept skills and the five paths

What the Builder can never do, whatever the AI writes: run anything itself (each step is a Guardian action), raise a tier (a
recipe or a path is only known orders, decided by policy.yaml), write outside the work folder or over a file, make a page that
reaches the network, or run code it wrote without your "yes" and PIN.
"""
