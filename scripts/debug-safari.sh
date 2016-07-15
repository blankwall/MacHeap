#!/bin/bash
match="WebContent"
declare -a old new
old=(`pgrep "$match" | sort -n`)
/Applications/Safari.app/Contents/MacOS/SafariForWebKitDevelopment "$@" &
safari=$!
new=(`pgrep "$match" | sort -n`)

printf "Found safari: %d\n" "$safari"
ps -o pid,command -p "$safari"
old+=($safari)

declare -a diff
for o in ${old[@]}; do
    for n in ${new[@]}; do
        [ "$o" -ne "$n" ] && diff+=($n)
    done
done
diff=(`echo "${diff[@]}" | tr ' ' $'\n' | sort -n | uniq`)

if [ ${#diff[@]} -eq 0 ]; then
    printf "Some kind of error. No new processes have been spawned.\n"
    printf "old: %s\nnew: %s\n" "${old[@]}" "${new[@]}"
    kill "$safari" 2>/dev/null
    exit 1
fi

printf "Found %d new processes: %s\n" "${#diff[@]}" "${diff[@]}"
ps -o pid,command -p `echo "${diff[@]}" | tr ' ' ','`

if [ ${#diff[@]} -ge 1 ]; then
    pid=${diff[0]}
    printf "Attaching to %d\n" "$pid"
    lldb -p "$pid"
    res=$?
    kill "$safari" 2>/dev/null
    exit $?
fi

printf "Not sure which pid to attach to. Terminating safari %d.\n" "$safari"
kill "$safari" 2>/dev/null
exit 1
