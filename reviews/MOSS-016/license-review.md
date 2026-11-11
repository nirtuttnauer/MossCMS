# MOSS-016 — psycopg[binary] license review

This is not legal advice. QA (Product — QA and CI) records the final ruling. This file records the locked version, the license files inside the wheels, what LGPL-3.0 says about shipping an unmodified wheel in an image, and the concrete action taken here.

Read date for every external source below: 2026-11-11. Repository facts are from main `58a0f15fa5e75e446b210911d727340dc4ca67dd` unless a command says otherwise. Anything a source does not state is marked **unverified**.

## What MossCMS ships

`api/pyproject.toml` declares `license = "MIT"` and depends on `psycopg[binary]>=3.2.3` (line 15). `LICENSE` is the MIT license, copyright 2026 Nir Tuttnauer. `README.md` links that file with the words "MIT licensed". `api/app/main.py` sets FastAPI `license_info` to `{"name": "MIT", "identifier": "MIT"}`. `.github/workflows/docker.yml` sets the image label `org.opencontainers.image.licenses=MIT` when it publishes `nirtuttnauer/mosscms` for `linux/amd64` and `linux/arm64`.

`Dockerfile` builds the API on `python:3.12-slim` (Debian, glibc), runs `uv sync --locked --no-dev --no-install-project`, and copies `/app/.venv` into the runtime image. `docs/docker.md` says the app image is built from this checkout unless a published image is selected, and that published images support `linux/amd64` and `linux/arm64`.

The base-image package set (Debian packages inside `python:3.12-slim`) was not unpacked for this review. Licenses of those packages are **unverified**.

## Locked version

`api/uv.lock` resolves the extra to two packages, both 3.3.6, from `https://pypi.org/simple`:

| Package | Version | Distribution named in the lockfile | SHA-256 in the lockfile |
| --- | --- | --- | --- |
| psycopg | 3.3.6 | `psycopg-3.3.6-py3-none-any.whl` | `a1db9f7148b06a28606767efaca51fa6f9398c5c0a3810519be69d7000bdb631` |
| psycopg | 3.3.6 | sdist `psycopg-3.3.6.tar.gz` | `c081f2250df751a943036e42db6df4571c66cd0aabe8291a7a506512b12007d2` |
| psycopg-binary | 3.3.6 | `psycopg_binary-3.3.6-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` | `1679a1cb93fbe5a6d1fd58d82cbddcc6fcb8c61446ba7cae6eb2a7b19bc585de` |
| psycopg-binary | 3.3.6 | `psycopg_binary-3.3.6-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl` | `37d40450659401600e6d043ff586c89a71a69f33cbb8bcdba6cdb2569beecdbe` |

The lockfile records `psycopg-binary` as the `binary` extra when `implementation_name != 'pypy'`. Upload time on each of those files in the lockfile is 2026-09-18. PyPI JSON for both projects, read the same day, reports `license_expression` `LGPL-3.0-only`. The psycopg JSON lists the sdist above. The psycopg-binary JSON lists 66 files and no source distribution (`https://pypi.org/pypi/psycopg/3.3.6/json`, `https://pypi.org/pypi/psycopg-binary/3.3.6/json`).

The two wheels above are the Python 3.12 glibc wheels for the platforms named in the Docker workflow. Other wheels in the lockfile (musllinux, macOS, Windows, other Python versions) were not unpacked. Their bundled libraries are **unverified**.

## Commands

Hashes of the downloaded wheels matched the lockfile. Working directory `/tmp/moss016`.

```sh
curl -fsSL -o psycopg-3.3.6-py3-none-any.whl \
  https://files.pythonhosted.org/packages/4e/de/748bd7609c71cae5d737f0ba9192f19329f70180ecda8fff3cac02c5abe3/psycopg-3.3.6-py3-none-any.whl
curl -fsSL -o psycopg_binary-3.3.6-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl \
  https://files.pythonhosted.org/packages/0a/42/948bb3d2617795093512613fd96ba380e922992c7908fbc073858147d196/psycopg_binary-3.3.6-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
curl -fsSL -o aarch64.whl \
  https://files.pythonhosted.org/packages/99/47/93e823ff1b0088400703410939c9bda3e63ed9c850b3ee088e8769f4c10b/psycopg_binary-3.3.6-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
unzip -q -o psycopg-3.3.6-py3-none-any.whl -d pure
unzip -q -o psycopg_binary-3.3.6-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl -d bin
unzip -q -o aarch64.whl -d arm
find bin arm pure -iname '*licen*' -o -iname '*notice*' -o -iname '*sbom*'
sha256sum pure/psycopg-3.3.6.dist-info/licenses/LICENSE.txt \
  bin/psycopg_binary-3.3.6.dist-info/licenses/LICENSE.txt \
  arm/psycopg_binary-3.3.6.dist-info/licenses/LICENSE.txt
curl -fsSL -A "Mozilla/5.0" -o lgpl-3.0.txt https://www.gnu.org/licenses/lgpl-3.0.txt
curl -fsSL -A "Mozilla/5.0" -o gpl-3.0.txt https://www.gnu.org/licenses/gpl-3.0.txt
readelf -d bin/psycopg_binary/pq.cpython-312-x86_64-linux-gnu.so
readelf -d bin/psycopg_binary/_psycopg.cpython-312-x86_64-linux-gnu.so
readelf -d bin/psycopg_binary.libs/*.so*
strings -a bin/psycopg_binary.libs/libcrypto-2d1629ee.so.3 | rg "OpenSSL [0-9]"
strings -a arm/psycopg_binary.libs/libcrypto-02bae65c.so.1.1.1k | rg "OpenSSL [0-9]"
strings -a arm/psycopg_binary.libs/libcrypto-cff3d539.so.3 | rg "OpenSSL [0-9]"
```

`cmp` of the three wheel `LICENSE.txt` files reported them identical. Python then reported those bytes equal to `lgpl-3.0.txt` (7,652 bytes, SHA-256 `e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118`). The same digest matches `https://raw.githubusercontent.com/psycopg/psycopg/3.3.6/LICENSE.txt` and `https://raw.githubusercontent.com/psycopg/psycopg/3.3.6/psycopg_c/LICENSE.txt`. `gpl-3.0.txt` is 35,149 bytes, SHA-256 `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`.

RPM License tags were read with `rpm -qp --queryformat '%{NAME}-%{VERSION}-%{RELEASE} | %{LICENSE}\n'` after `curl` of the URLs in the tables below. The aarch64 wheel's SBOM names EL8 package name-version-releases. The License tags were read from x86_64 RPMs of those same name-version-releases. The aarch64 RPM headers were not downloaded.

## License files inside the wheels

Each wheel's `*.dist-info/METADATA` says `License-Expression: LGPL-3.0-only` and `License-File: LICENSE.txt`. The copyright line in the description is `Copyright (C) 2020 The Psycopg Team`.

The license directory of each wheel contains one file, `LICENSE.txt`. That file is the GNU LGPL version 3 text and nothing after it: it ends at section 6, "Revised Versions of the GNU Lesser General Public License." A listing of the binary wheels finds no second license, COPYING, or NOTICE file. The x86_64 wheel `RECORD` names `psycopg_binary-3.3.6.dist-info/licenses/LICENSE.txt` and `psycopg_binary-3.3.6.dist-info/sboms/auditwheel.cdx.json`.

The SBOM is CycloneDX 1.4 written by auditwheel 6.7.0. Its components have names and versions and no `licenses` field. So the wheel's own license file states LGPL-3.0 for the Python package. It does not state a license for any bundled native library.

## Native libraries in the wheels

Both extension modules, `pq.*.so` and `_psycopg.*.so`, have `NEEDED` `libpq-*.so.5.18` and `RPATH` `$ORIGIN/../psycopg_binary.libs`. `libpq` has `RPATH` `$ORIGIN` and `NEEDED` entries for the bundled `libssl`, `libcrypto`, `libgssapi_krb5`, and `libldap`, plus system `libm`, `libpthread`, and `libc`. System libraries named by `NEEDED` and absent from `psycopg_binary.libs/` (`libc`, `libpthread`, `libm`, `libdl`, `libresolv`, `libz`) are not files in the wheel. Their licenses are **unverified** here.

`strings` on the x86_64 `libpq` file did not print a PostgreSQL version. The SONAME is `libpq-….so.5.18`. PostgreSQL `REL_18_6` `src/interfaces/libpq/Makefile` sets `SO_MAJOR_VERSION= 5` and `SO_MINOR_VERSION= $(MAJORVERSION)` (`https://raw.githubusercontent.com/postgres/postgres/REL_18_6/src/interfaces/libpq/Makefile`). `MAJORVERSION` comes from `PG_MAJORVERSION` in `src/Makefile.global.in` on that tag. The psycopg tag's wheel workflow pins `LIBPQ_VERSION: "18.6"` and `tools/ci/build_libpq.sh` downloads `https://github.com/postgres/postgres/archive/REL_18_6.tar.gz`, applies a patch that changes the default `gssencmode` to `disable` and the default socket directory, then builds `src/interfaces/libpq`. The patch-level identity of the bytes inside the wheel is that build pin. A version string inside the `.so` is **unverified**.

The same script and `.github/workflows/packages-bin.yml` at tag 3.3.6 pin `OPENSSL_VERSION: "3.5.8"` and build OpenSSL from `https://github.com/openssl/openssl/archive/openssl-3.5.8.tar.gz`. Both wheels contain a `libcrypto.so.3` whose strings include `OpenSSL 3.5.8 25 Aug 2026`. The tag commit `a67654d1e7afbf9b3a619557838f62de1c790e7c` is dated 2026-09-18T11:21:29Z (`https://api.github.com/repos/psycopg/psycopg/commits/3.3.6`), the same day the lockfile records the wheel upload.

On Linux the script builds OpenLDAP when `ID` is centos, rocky, almalinux, or macos, from `openldap-2.6.14.tgz`, and builds Kerberos from source on macOS. It installs `krb5-devel` from the distro on centos, almalinux, and rocky. That matches the wheels: `libldap` and `liblber` are present and absent from the RPM SBOM, while Kerberos, SASL, PCRE, keyutils, libselinux, and libcom_err are SBOM RPM components. No OpenLDAP version string was found in `libldap`. The 2.6.14 identification is the build script. An embedded version is **unverified**.

manylinux images differ by architecture in that workflow: x86_64 uses `manylinux2014`, aarch64 uses `manylinux_2_28`. The SBOM package sets differ in the same way.

### linux/amd64, cp312 manylinux2014

| Wheel file | How it was identified | License stated by the cited source |
| --- | --- | --- |
| `libpq-e9b5c9ac.so.5.18` | SONAME; build pin 18.6 | PostgreSQL License, https://www.postgresql.org/about/licence/ |
| `libssl-8bd944e8.so.3`, `libcrypto-2d1629ee.so.3` | string `OpenSSL 3.5.8 25 Aug 2026` | Apache License 2.0, https://raw.githubusercontent.com/openssl/openssl/openssl-3.5.8/LICENSE.txt |
| `libgssapi_krb5-497db0c6.so.2.2`, `libk5crypto-b1f99d5c.so.3.1`, `libkrb5-fcafa220.so.3.3`, `libkrb5support-d0bcff84.so.0.1` | SBOM `krb5-libs` `1.15.1-55.el7_9` | MIT. RPM: https://vault.centos.org/7.9.2009/updates/x86_64/Packages/krb5-libs-1.15.1-55.el7_9.x86_64.rpm |
| `libkeyutils-dfe70bd6.so.1.5` | SBOM `keyutils-libs` `1.5.8-3.el7` | `GPLv2+ and LGPLv2+`. RPM: https://vault.centos.org/7.9.2009/os/x86_64/Packages/keyutils-libs-1.5.8-3.el7.x86_64.rpm |
| `libcom_err-2abe824b.so.2.1` | SBOM `libcom_err` `1.42.9-19.el7` | MIT. RPM: https://vault.centos.org/7.9.2009/os/x86_64/Packages/libcom_err-1.42.9-19.el7.x86_64.rpm |
| `libldap-7c3a4b12.so.2.0.200`, `liblber-a44a5afb.so.2.0.200` | present; absent from the SBOM; build pin OpenLDAP 2.6.14 | OpenLDAP Public License Version 2.8, 17 August 2003. https://raw.githubusercontent.com/openldap/openldap/OPENLDAP_REL_ENG_2_6_14/LICENSE and https://www.openldap.org/software/release/license.html |
| `libpcre-9513aab5.so.1.2.0` | string `8.32 2012-11-30`; SBOM `pcre` `8.32-17.el7` | BSD. RPM: https://vault.centos.org/7.9.2009/os/x86_64/Packages/pcre-8.32-17.el7.x86_64.rpm |
| `libsasl2-84219a89.so.3.0.0` | string `Cyrus SASL` and `2.1.26`; SBOM `cyrus-sasl-lib` `2.1.26-24.el7_9` | `BSD with advertising`. RPM: https://vault.centos.org/7.9.2009/updates/x86_64/Packages/cyrus-sasl-lib-2.1.26-24.el7_9.x86_64.rpm |
| `libselinux-0922c95c.so.1` | SBOM `libselinux` `2.5-15.el7` | Public Domain. RPM: https://vault.centos.org/7.9.2009/os/x86_64/Packages/libselinux-2.5-15.el7.x86_64.rpm |
| `libcrypt-bc2db45e.so.1` | file in the wheel; absent from the SBOM; `strings` printed no license and no package version | **unverified** |

### linux/arm64, cp312 manylinux_2_28

`libpq` again has SONAME `libpq.so.5.18` and `NEEDED` OpenSSL 3 (`libssl-c64c0f6b.so.3`, `libcrypto-cff3d539.so.3`), whose strings include `OpenSSL 3.5.8 25 Aug 2026`. The same PostgreSQL and Apache-2.0 sources apply. `libldap` and `liblber` are again present and absent from the SBOM; the same OpenLDAP build pin and license apply, with the embedded version **unverified**.

| Wheel file | How it was identified | License stated by the cited source |
| --- | --- | --- |
| `libcrypto-02bae65c.so.1.1.1k` | SONAME and string `OpenSSL 1.1.1k  FIPS 25 Mar 2021`; SBOM `openssl-libs` `1.1.1k-17.el8_6`. `readelf -d` shows the Kerberos libraries `NEEDED` this file. `libpq` `NEEDED` the OpenSSL 3 libraries, not this one. | OpenSSL License and original SSLeay license, https://raw.githubusercontent.com/openssl/openssl/OpenSSL_1_1_1k/LICENSE . The RPM License tag for `openssl-libs-1.1.1k-17.el8_6` was not retrieved (vault URL returned 404). That tag is **unverified**. |
| `libgssapi_krb5`, `libk5crypto`, `libkrb5`, `libkrb5support` | SBOM `krb5-libs` `1.18.2-34.el8_10` | MIT. https://dl.rockylinux.org/pub/rocky/8/BaseOS/x86_64/os/Packages/k/krb5-libs-1.18.2-34.el8_10.x86_64.rpm |
| `libkeyutils-fe6e95a9.so.1.6` | SBOM `keyutils-libs` `1.5.10-9.el8` | `GPLv2+ and LGPLv2+`. https://dl.rockylinux.org/pub/rocky/8/BaseOS/x86_64/os/Packages/k/keyutils-libs-1.5.10-9.el8.x86_64.rpm |
| `libcom_err-6d8d18aa.so.2.1` | SBOM `libcom_err` `1.45.6-7.el8_10` | MIT. https://dl.rockylinux.org/pub/rocky/8/BaseOS/x86_64/os/Packages/l/libcom_err-1.45.6-7.el8_10.x86_64.rpm |
| `libpcre2-8-8701a61e.so.0.7.1` | SBOM `pcre2` `10.32-3.el8_6` | BSD. https://dl.rockylinux.org/pub/rocky/8/BaseOS/x86_64/os/Packages/p/pcre2-10.32-3.el8_6.x86_64.rpm |
| `libsasl2-076b3c1f.so.3.0.0` | string `Cyrus SASL` / `2.1.27` and a debug path ending in `2.1.27-6.el8_5.aarch64`; SBOM `cyrus-sasl-lib` `2.1.27-6.el8_5` | `BSD with advertising`. https://dl.rockylinux.org/pub/rocky/8/BaseOS/x86_64/os/Packages/c/cyrus-sasl-lib-2.1.27-6.el8_5.x86_64.rpm |
| `libselinux-be7a4dc7.so.1` | SBOM `libselinux` `2.9-11.el8_10` | Public Domain. https://dl.rockylinux.org/pub/rocky/8/BaseOS/x86_64/os/Packages/l/libselinux-2.9-11.el8_10.x86_64.rpm |
| `libcrypt-258f54d5.so.1.1.0` | SBOM `libxcrypt` `4.1.1-6.el8` | `LGPLv2+ and BSD and Public Domain`. https://vault.centos.org/8.5.2111/BaseOS/x86_64/os/Packages/libxcrypt-4.1.1-6.el8.x86_64.rpm |

The keyutils RPM tag covers the package. The wheel contains `libkeyutils` and no license file that assigns the shared library to the GPL line or the LGPL line. Which of those two tags applies to the `.so` alone is **unverified**.

## What LGPL-3.0 says about an unmodified wheel in an image

The wheel `LICENSE.txt` is the LGPL-3.0 text quoted here. The same sentences are in https://www.gnu.org/licenses/lgpl-3.0.txt . Section 4, "Combined Works":

> You may convey a Combined Work under terms of your choice that, taken together, effectively do not restrict modification of the portions of the Library contained in the Combined Work and reverse engineering for debugging such modifications, if you also do each of the following:
>
> a) Give prominent notice with each copy of the Combined Work that the Library is used in it and that the Library and its use are covered by this License.
>
> b) Accompany the Combined Work with a copy of the GNU GPL and this license document.
>
> c) For a Combined Work that displays copyright notices during execution, include the copyright notice for the Library among these notices, as well as a reference directing the user to the copies of the GNU GPL and this license document.
>
> d) Do one of the following:
>
> 0) Convey the Minimal Corresponding Source under the terms of this License, and the Corresponding Application Code in a form suitable for, and under terms that permit, the user to recombine or relink the Application with a modified version of the Linked Version to produce a modified Combined Work, in the manner specified by section 6 of the GNU GPL for conveying Corresponding Source.
>
> 1) Use a suitable shared library mechanism for linking with the Library. A suitable mechanism is one that (a) uses at run time a copy of the Library already present on the user's computer system, and (b) will operate properly with a modified version of the Library that is interface-compatible with the Linked Version.
>
> e) Provide Installation Information, but only if you would otherwise be required to provide such information under section 6 of the GNU GPL, and only to the extent that such information is necessary to install and execute a modified version of the Combined Work produced by recombining or relinking the Application with a modified version of the Linked Version.

Section 0 defines a Combined Work as "a work produced by combining or linking an Application with the Library." The image build installs the wheel and copies the virtualenv next to the MossCMS application. MossCMS does not patch the wheel files. The wheel `RECORD` includes `LICENSE.txt`, so a wheel install that follows `RECORD` places the LGPL text in the virtualenv. This review did not `docker build` and then list that path inside an image, so the in-image path is **unverified** by an image listing. The Dockerfile and the `RECORD` are the sources for how the file would get there.

Section 4(d)(0) points at GPL-3.0 section 6, "Conveying Non-Source Forms" (https://www.gnu.org/licenses/gpl-3.0.txt):

> You may convey a covered work in object code form under the terms of sections 4 and 5, provided that you also convey the machine-readable Corresponding Source under the terms of this License, in one of these ways:

The five ways in that section are: source fixed with the object code on a physical medium; a written offer, valid for at least three years, to give the source on a physical medium or from a network server; passing on such an offer for occasional noncommercial copies; offering the object code from a designated place and equivalent access to the source at no further charge, with clear directions next to the object code saying where to find the source; and peer-to-peer transmission that tells peers about a section 6(d) offer. The same section defines a User Product and when Installation Information must accompany the source. Whether a MossCMS image is a User Product under that definition is **unverified**.

### Notice, license text, and replacing the library

Prominent notice. The MIT license file, the README line, the OpenAPI `license_info`, and the published image label name MIT. They do not name psycopg or LGPL-3.0. The LGPL text is the wheel's own `LICENSE.txt`. Section 4(a) asks for prominent notice with each copy of the Combined Work. `NOTICE` at the repository root is that notice for people who receive the checkout. The Dockerfile copies the virtualenv, `api/app`, migrations, `shared/`, and the built admin. It does not copy `NOTICE`. A copy of this notice inside the image needs a Dockerfile change. That change is outside this ticket.

License text. Section 4(b) asks the distributor to accompany the Combined Work with a copy of the GNU GPL and the LGPL. The wheel contains the LGPL text. The wheel file listing contains no GPL-3.0 text. Apache-2.0 section 4(a), in the OpenSSL 3.5.8 `LICENSE.txt`, says recipients of the work must be given a copy of that license. The OpenSSL 1.1.1k `LICENSE` says binary redistributions must reproduce the copyright notice, the conditions, and the disclaimer, and its condition 3 says advertising materials that mention features or use of the software must display the OpenSSL acknowledgment. The PostgreSQL License says the copyright notice and the following paragraphs appear in all copies. The OpenLDAP Public License says redistributions must contain a verbatim copy of that document. None of those texts are files in the wheel. Copying them into the image is a Dockerfile change and is not done here.

Replacing the library. The extension is linked to a shared `libpq` with RPATH `$ORIGIN/../psycopg_binary.libs`, and that `libpq` is linked to the other bundled shared objects with RPATH `$ORIGIN`. The libraries are separate files in the wheel, not absorbed into the extension. Section 4(d)(1) describes a suitable mechanism as one that uses, at run time, a copy of the Library already present on the user's computer system, and that will operate with a modified interface-compatible version. The license text states that test. It does not state that an auditwheel directory with `$ORIGIN` RPATH meets the test. Whether this layout meets section 4(d)(1) is **unverified**.

psycopg's installation documentation (https://www.psycopg.org/psycopg3/docs/basic/install.html , page title "Installation - psycopg 3.3.9.dev1 documentation", read 2026-11-11) says a local installation "will be linked to the system libraries (`libpq`, `libssl`…) so that system upgrade of libraries will upgrade the libraries used by Psycopg 3 too. This is the preferred way to install Psycopg for a production site." The same page says the binary installation "will install a self-contained package with all the libraries needed." Switching MossCMS from `psycopg[binary]` to that local installation would change the dependency and the image. This ticket does not allow that change.

If section 4(d)(0) is the applicable branch, corresponding source has to be conveyed in one of the GPL section 6 ways. The psycopg 3.3.6 sdist is the URL in the lockfile. psycopg-binary 3.3.6 has no sdist on PyPI. At tag 3.3.6, `tools/ci/copy_to_binary.py` states that it creates the psycopg-binary package by copying `psycopg_c` and renaming it, and `packages-bin.yml` runs that script before building the wheel. The image build does not copy that source tree and does not write directions next to the installed wheel. Whether the public sdist and git tag, without directions in the image, meet GPL section 6 is **unverified**.

Section 4(c) applies to a Combined Work that displays copyright notices during execution. The running API serves an OpenAPI document whose `license_info` names MIT. Whether that field is a copyright notice displayed during execution is **unverified**. The application source under `api/app` has no other copyright banner. Changing `license_info` is outside the file list for this ticket.

## MIT license of MossCMS and this dependency

Section 4 of the LGPL text quoted above says a Combined Work may be conveyed under terms of the distributor's choice when the conditions in that section are met, and those terms, taken together, effectively do not restrict modification of the Library portions or reverse engineering for debugging such modifications. The sources read here state the MIT terms for MossCMS's own files and the LGPL-3.0-only expression for the psycopg wheels. They do not state that the dependency replaces the MIT license of MossCMS's own code. They also do not state that the MIT file by itself fulfills section 4. `LICENSE` is unchanged. No license exception is added.

The psycopg 3.3.6 `LICENSE.txt` contains no additional OpenSSL exception paragraph. The file is the GNU text.

## Conclusion

A root `NOTICE` is required by the material above: section 4(a) asks for prominent notice with each copy of the Combined Work, and the existing MIT license file, README line, OpenAPI field, and image label do not name this library. `NOTICE` is added at the repository root. It names psycopg 3.3.6 and psycopg-binary 3.3.6, the LGPL-3.0-only expression, the path of the LGPL text inside the wheels, the native libraries and the license names sourced above, and the sdist and git tag for the sources. It states that this is not legal advice, that QA records the final ruling, and that it adds no license exception.

Still to do, outside this ticket's file list:

- A Dockerfile change that copies `NOTICE`, the GPL-3.0 text, the LGPL-3.0 text, and the license texts of the bundled native libraries into the image.
- The image label and the OpenAPI `license_info` still name MIT alone. Whether either should also name the LGPL library is part of the ruling QA records.
- QA can decide later whether a production image should use the local psycopg build the project documentation prefers. That would change the dependency and the image, which this ticket leaves alone.

QA (Product — QA and CI) records the final ruling. This review does not.
