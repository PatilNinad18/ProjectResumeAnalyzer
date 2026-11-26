with open(r"d:\smartleaven\ProjectResumeAnalyzer\frontend\src\components\screening\CandidateLeaderboard.tsx", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, l in enumerate(lines[63:95], 63):
    print(f"{i}: {repr(l)}")
