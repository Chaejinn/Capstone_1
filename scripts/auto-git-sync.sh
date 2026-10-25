#!/bin/zsh

set -u

repo_dir="${0:A:h:h}"
cd "$repo_dir" || exit 1

echo "[auto-git] 감시 시작: $repo_dir"

while true; do
  # 병합/리베이스 중인 파일이나 다른 작업 브랜치는 자동 커밋하지 않는다.
  if [[ "$(git branch --show-current)" != "main" ]] ||
     [[ -f "$(git rev-parse --git-path MERGE_HEAD)" ]] ||
     [[ -d "$(git rev-parse --git-path rebase-merge)" ]] ||
     [[ -d "$(git rev-parse --git-path rebase-apply)" ]]; then
    sleep 5
    continue
  fi
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

  # 양쪽 저장소를 독립적으로 반영한다. 한쪽 실패 시 다른 쪽은 계속 처리한다.
  # 강제 push나 자동 pull/병합은 하지 않는다.
  for remote_name in origin drownguardian; do
    if ! git remote get-url "$remote_name" >/dev/null 2>&1; then
      echo "[auto-git] 원격 없음: $remote_name — README의 동기화 설정을 확인하세요."
      continue
    fi
    if [[ "$(git rev-parse HEAD)" != "$(git rev-parse "refs/remotes/$remote_name/main" 2>/dev/null)" ]]; then
      if git push "$remote_name" HEAD:refs/heads/main; then
        echo "[auto-git] $remote_name/main 반영 완료"
      else
        echo "[auto-git] $remote_name push 실패 — 다음 주기에 재시도합니다. 원격 변경이 있으면 수동 병합이 필요합니다."
      fi
    fi
  done

  sleep 5
done
