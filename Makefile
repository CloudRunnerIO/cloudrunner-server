REV := $(shell ./scripts/rpm/getrev.sh .)
# Remove - and . from branch - we cannot add them into Revision
BRANCH := $(shell ./scripts/rpm/getbranch.sh | sed 's|-|_|' | sed 's|\.||')

VERSION := $(shell ./scripts/rpm/getrev.sh | cut -d "." -f 1-3 )
RELEASE := $(shell ./scripts/rpm/getrev.sh | cut -d "." -f 4 )

SRC=src/
PY=`python -c 'import sys; print sys.version[:3]'`
__python=$(shell V=$$(python -V 2>&1 | awk '{ print $$2 }' | sed 's/\(.*\)\..*/\1/g'); if [[ "$$V" < '2.6' ]]; then echo 'python2.6'; else echo 'python$$PY'; fi)

# Default target executed when no arguments are given to make.
.PHONY : default_target
default_target: all

.PHONY: all
all: sdist prepare
	./scripts/rpm/rpm-mock.sh epel-6-x86_64
	./scripts/rpm/rpm-mock.sh epel-7-x86_64
	./scripts/rpm/rpm-mock.sh fedora-19-x86_64
	./scripts/rpm/rpm-mock.sh fedora-20-x86_64
	./scripts/rpm/rpm-mock.sh fedora-21-x86_64
	rm -rf cloudrunner_server.spec

.PHONY: sdist
sdist: clean
	rm -rf dist/cloudrunner-server*.tar.gz
	$(__python) setup.py sdist

.PHONY: rpm
rpm: sdist
	rm -rf ~/rpmbuild/SOURCES/cloudrunner_server*.tar.gz
	rm -rf ~/rpmbuild/RPMS/noarch/cloudrunner-server*.rpm
	rm -rf ~/rpmbuild/SRPMS/cloudrunner-server*.src.rpm
	cp dist/cloudrunner_server*.tar.gz ~/rpmbuild/SOURCES/
	cp cloudrunner-server.spec.in cloudrunner_server.spec
	sed -i 's/^Release:.*/Release:        $(RELEASE)%{?dist}/g' cloudrunner_server.spec
	sed -i 's/^Version:.*/Version:        $(VERSION)/g' cloudrunner_server.spec
	rpmbuild -ba cloudrunner_server.spec
	rm cloudrunner_server.spec

.PHONY: prepare
prepare:
	cp cloudrunner-server.spec.in cloudrunner_server.spec
	sed -i 's/^Release:.*/Release:        $(RELEASE)%{?dist}/g' cloudrunner_server.spec
	sed -i 's/^Version:.*/Version:        $(VERSION)/g' cloudrunner_server.spec

.PHONY: rpm-el6_x64
rpm-el6_x64: sdist prepare
	./scripts/rpm/rpm-mock.sh epel-6-x86_64
	rm cloudrunner_server.spec

.PHONY: rpm-el7_x64
rpm-el7_x64: sdist prepare
	./scripts/rpm/rpm-mock.sh epel-7-x86_64
	rm cloudrunner_server.spec

.PHONY: rpm-el6_el7_x64
rpm-el6_el7_x64: sdist prepare
	./scripts/rpm/rpm-mock.sh epel-6-x86_64
	./scripts/rpm/rpm-mock.sh epel-7-x86_64
	rm cloudrunner_server.spec

.PHONY: rpm-f19_x64
rpm-f19_x64: sdist prepare
	./scripts/rpm/rpm-mock.sh fedora-19-x86_64
	rm cloudrunner_server.spec

.PHONY: rpm-f20_x64
rpm-f20_x64: sdist prepare
	./scripts/rpm/rpm-mock.sh fedora-20-x86_64
	rm cloudrunner_server.spec

.PHONY: rpm-f21_x64
rpm-f21_x64: sdist prepare
	./scripts/rpm/rpm-mock.sh fedora-21-x86_64
	rm cloudrunner_server.spec

.PHONY: clean
clean:
	##  $(__python) setup.py develop --uninstall --install-dir . -m
	echo "Remove other temporary files..."
	rm -rf easy_install* src/*.egg-info .coverage
	rm -rf build

.PHONY: test
test:
	tox
