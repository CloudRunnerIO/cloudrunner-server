#!/bin/bash

MAJOR=$(python -c "from cloudrunner_server.version import VERSION; print VERSION");
if [ "$(git branch |grep "\*" |grep master )" ] ;then
    MINOR=$(git log --pretty=format:'%ad %h %d' --abbrev-commit --date=iso -1|awk {'print $1"-"$2"_"$4'}|sed -e 's/[-:]//g');
else
    MINOR=$(git branch -r | grep stable/ | sort | tail -n1 | cut -d "/" -f3);
fi

echo ${MAJOR}.${MINOR} > $(dirname $0)/../../VERSION;
cat  $(dirname $0)/../../VERSION 2> /dev/null ||echo unknown
