REV := $(shell ./scripts/rpm/getrev.sh .)
BRANCH := $(shell ./scripts/rpm/getbranch.sh)
SRC=src/
PY=`python -c 'import sys; print sys.version[:3]'`
__python=$(shell V=$$(python -V 2>&1 | awk '{ print $$2 }' | sed 's/\(.*\)\..*/\1/g'); if [[ "$$V" < '2.6' ]]; then echo 'python2.6'; else echo 'python$$PY'; fi)

# Default target executed when no arguments are given to make.
.PHONY : default_target
default_target: all


.PHONY: all
all: clean
	$(__python) setup.py build
        ## _last_ ## $(__python) setup.py develop --install-dir . -m


.PHONY: sdist
sdist: clean
	rm -rf dist/cloudrunner_server*.tar.gz
	$(__python) setup.py sdist


.PHONY: rpm
rpm: sdist
	rm -rf ~/rpmbuild/SOURCES/cloudrunner_server*.tar.gz
	rm -rf ~/rpmbuild/RPMS/noarch/cloudrunner_server*.rpm
	rm -rf ~/rpmbuild/SRPMS/cloudrunner_server*.src.rpm
	cp dist/cloudrunner_server*.tar.gz ~/rpmbuild/SOURCES/
	cp cloudrunner_server.spec.in cloudrunner_server.spec
	sed -i 's/^Release:.*/Release:        $(REV).$(BRANCH)%{?dist}/g' cloudrunner_server.spec
	rpmbuild -ba cloudrunner_server.spec
	rm cloudrunner_server.spec

.PHONY: rpm-el5_64
rpm-el5_64: sdist
	./scripts/rpm/rpm-mock.sh epel-5-x86_64

.PHONY: rpm-el6_64
rpm-el6_64: sdist
	./scripts/rpm/rpm-mock.sh epel-6-x86_64

.PHONY: rpm-f19_64
rpm-f19_64: sdist
	./scripts/rpm/rpm-mock.sh fedora-19-x86_64

.PHONY: rpm-el5_32
rpm-el5_32: sdist
	./scripts/rpm/rpm-mock.sh epel-5-i386

.PHONY: rpm-el6_32
rpm-el6_32: sdist
	./scripts/rpm/rpm-mock.sh epel-6-i386

.PHONY: rpm-f19_32
rpm-f19_32: sdist
	./scripts/rpm/rpm-mock.sh fedora-19-i386

.PHONY: docs
docs: sdist
	$(__python) setup.py build_sphinx 

.PHONY: userinstall
userinstall: gen_stubs
	$(__python) setup.py install --user

.PHONY: clean
clean:
	##  $(__python) setup.py develop --uninstall --install-dir . -m
	echo "Remove other temporary files..."
	rm -rf easy_install* src/*.egg-info .coverage
	rm -rf build
