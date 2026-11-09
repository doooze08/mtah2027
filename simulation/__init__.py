"""Simulation test bench: scripted football clips with known possession answers.

Pipeline (each stage only reads what the previous stage hands it):

    script (scenarios/<family>.py)  ->  clean clip + truth (core/clip.py, core/events.py)
        ->  observation layer (core/observe.py)  ->  algorithm  ->  scoring (evaluate.py)

See simulation/README.md for the file layout and simulation/scenarios/SCENARIOS.md
for what each scenario is meant to test.
"""
