# Git workflow

One rule above everything else: before you run `git add` or `git commit`, run `git status` first and check the top line. If it says `On branch main`, stop, you're in the wrong place.

## One time only, when you first set up the project on your laptop

```
git clone https://github.com/stuckingravity/hod102-2026-group-4.git
cd hod102-2026-group-4
```

## Every day you sit down to work

First decide: are you continuing the task you already have a branch for, or starting something brand new?

**Continuing** (this is almost every day for us, since each person has one assigned task):
```
git checkout feature/your-task-name
```

**Starting a brand new task** (rare, only happens if you finish early and pick up another one):
```
git checkout main
git pull origin main
git checkout -b feature/your-task-name
```

Either way, once you're on the right branch:
```
git add .
git commit -m "short description of what you did"
git push
```

First push from a brand new branch needs `git push -u origin feature/your-task-name` instead of plain `git push`. After that, plain `git push` works.

## When the task is ready

On GitHub: open a pull request, base `main`, compare `feature/your-task-name`. Add reviewers and click **Create pull request**, the button actually has to be clicked, filling in the title and reviewers alone doesn't send anything. Wait for approval, then merge.

## After it's merged

```
git checkout main
git pull origin main
git branch -d feature/your-task-name
```

This is the only point where the branch gets deleted, and it only happens once, right after the merge. Every day before this, from the moment you created the branch until now, you were reusing that same branch with the plain `checkout` command above, that's what "continuing" meant. Once it's deleted here, that branch is finished for good, there's nothing left to switch back to. If more work comes up later, even on a related topic, that's a new task with a new branch, back at the top under "Every day you sit down to work."

---

If it's been a day or two since you branched off and you're worried main has moved, you can pull it into your branch any time:

```
git checkout feature/your-task-name
git merge main
```

Not required, just catches conflicts early instead of at PR time.

## Task branches

`feature/skeleton`, `feature/chat-ui`, `feature/coach-logic`, `feature/plan-generation`, `feature/screens-data`

This is just the agreed naming so everyone uses the same convention, not a live status list, branches get deleted once merged.
