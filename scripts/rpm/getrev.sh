#!/bin/bash

if [ -d .svn ]; then
    URL="$(svn info | grep '^URL: ' | cut -c 6- | tr -d ':@[](){}-')"
    echo "${URL##*/}"|sed 's/^[0-9]*.[0-9]*_//' > VERSION
elif [ -d '.git' ]; then
# when we start using tags will enable this sectip

    # We use git, take the short sha string
    # ( git describe --long | cut  -c 2- | cut -d "-" -f 1 || echo 'unknown' ) > VERSION
    #(( ver=$(git describe --long) && ver=${ver#*-} && echo ${ver/-/.} ) || echo unknown) > `dirname $0`/../../VERSION
    var=
fi

if [ ! -z $ver ] ;then
    cat  `dirname $0`/../../VERSION 2> /dev/null ||echo unknown
fi

if [ -z $ver ] ;then
    # If we are here - Most propably we do not have tags, so will use date-commit for revision
    # We use git, take the date and short sha string
    (( ver=$(git log --pretty=format:'%ad %h %d' --abbrev-commit --date=iso -1|awk {'print $1"_"$2"."$4'}|sed -e 's/-/_/g' | sed -e 's/\:/./g') && echo ${ver}) || echo unknown ) > `dirname $0`/../../VERSION
fi

cat  `dirname $0`/../../VERSION 2> /dev/null ||echo unknown

