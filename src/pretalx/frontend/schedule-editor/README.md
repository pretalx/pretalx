<!--
SPDX-FileCopyrightText: 2022-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

# pretalx-schedule-editor

## Project setup
```
npm ci
```

### Compiles and hot-reloads for development
```
npm start
```

### Compiles and minifies for production
```
npm run build
```

In a pretalx checkout this is run for you by ``python manage.py rebuild``,
which sets ``OUT_DIR`` and ``BASE_URL`` so that the build output lands in
Django's ``STATIC_ROOT`` and is picked up via the
``pretalx-manifest.json`` manifest.

### Lints and fixes files
```
npm run lint
```
