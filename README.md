# CV as code

A **CV generator** (one-page A4 PDFs, checked for ATS robots) and a private **job-application board**, in one repo.

![A CV built from a text profile (fictional example)](docs/images/cv-demo.png)

![The application board: one column per hiring stage, cards filtered by the CV sent](docs/images/tracker.png)

## Start

**Use this template** on GitHub, create the copy as a **private** repo, then:

```
cp -R profiles/_template profiles/<you>   # edit profiles/<you>/content.js
./build.sh <you>                          # -> out/<you>/*.pdf
./tracker.sh                              # -> http://127.0.0.1:8765/
```

