#!/bin/zsh

set -u

repo_dir="${0:A:h:h}"
cd "$repo_dir" || exit 1

echo "[auto-git] 감시 시작: $repo_dir"

while true; do
  if [[ -n "$(git status --porcelain)" ]]; then
    # 연속 저장을 하나의 커밋으로 묶는다.
    sleep 5
    git add -A

    if ! git diff --cached --quiet; then
      commit_time="$(date '+%Y-%m-%d %H:%M:%S')"
      if git commit -m "Auto update: $commit_time"; then
        echo "[auto-git] 커밋 완료: $commit_time"
      else
        echo "[auto-git] 커밋 실패 — 다음 주기에 재시도합니다."
      fi
    fi
  fi

  # 네트워크 문제 등으로 이전 push가 실패했어도 계속 재시도한다.
  if [[ "$(git rev-list --count '@{upstream}..HEAD' 2>/dev/null || echo 0)" -gt 0 ]]; then
    if git push; then
      echo "[auto-git] GitHub 반영 완료"
    else
      echo "[auto-git] push 실패 — 다음 주기에 재시도합니다."
    fi
  fi

  sleep 5
done
