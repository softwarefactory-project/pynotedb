%global         sum A NoteDb helper library.

Name:           pynotedb
Version:        0.0.1
Release:        1%{?dist}
Summary:        %{sum}

License:        ASL 2.0
URL:            https://docs.softwarefactory-project.io/%{name}
Source0:        https://tarballs.softwarefactory-project.io/%{name}/%{name}-%{version}.tar.gz

BuildArch:      noarch

Buildrequires:  python3-devel
Buildrequires:  python3-wheel
Buildrequires:  python3-setuptools-scm

Requires:       python3

%description
%{sum}

%prep
%autosetup -n pynotedb-%{version}

%build
SETUPTOOLS_SCM_PRETEND_VERSION=%{version} %{__python3} setup.py build

%install
SETUPTOOLS_SCM_PRETEND_VERSION=%{version} %{__python3} setup.py install --skip-build --root %{buildroot}

%files
%{python3_sitelib}/*
%{_bindir}/*

%changelog
* Wed Sep  2 2020 Tristan Cacqueray <tdecacqu@redhat.com> - 0.0.1-1
- Initial packaging
