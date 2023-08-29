# build-and-push-buildkite-plugin

A concise plugin to assist with build multi-arch container images and pushing them to an ECR repository.

Subsequent pipeline steps can `depend_on` the step key: `build-and-push` to ensure that image building and pushing is complete before continuing (see [`group-key`](#group-key-string) for configuring this value).

## Usage
```yaml
steps:
  - plugins:
    - ssh://git@github.com/CatchoftheDay/build-and-push-buildkite-plugin.git#v1.2.0: ~
```

## Configuration
All configuration is optional.

```yaml
steps:
  - plugins:
    - ssh://git@github.com/CatchoftheDay/build-and-push-buildkite-plugin.git#v1.2.0:
        dockerfile-path: app/Dockerfile
        context-path: "."
        image-name: my-super-special-application
        image-tag: latest
        additional-tag: $BUILDKITE_BUILD_NUMBER
        build-args: "secret-from-vault,not-a-secret=42"
        build-arm: true
        build-x86: true
        scan-image: true
        group-key: build-and-push-0.0.1
        always-pull: false
```


### `dockerfile-path` [string]
The relative path of the Dockerfile from the project root. Default: `Dockerfile`

### `context-path` [string]
The path used as the root of the docker build environment. This effects the source location and availablility of files referenced with `ADD` in the Dockerfile. Default: `.` (the project root)

### `image-name` [string]
The name of your application image. Will be prefixed with `catch/` before being pushed to the registry. Default: Buildkite pipeline name (`$BUILDKITE_PIPELINE_NAME`).

### `image-tag` [string]
A container image tag. Default: First 10 characters of git SHA.

### `additional-tag` [string]
An additional tag for the image, useful if the main tag is dynamic or vis-versa. Default: None

### `build-args` [comma-delimited list]
Additional build-arguments (`--build-arg`) to pass to `docker build`. These can be single values (ideally used for secrets that are available to every pipeline step as env vars) or key=value pairs which can be used to pass in non-secret values that aren't known to every step of the pipeline. Default: `""`, `GITHUB_TOKEN` is always provided.

### `push-branches` [comma-delimited list]
A list of branch names for which to push a built image to ECR. This can serve as a toggle to be able to test container builds in feature branches but only push those images to ECR for deployable branches. If the build is triggered from a non-branch event (such as a git tag) it will always be pushed to ECR. Default: `""`

### `build-arm` [boolean]
Should we build an ARM image? Default: `true`

### `build-x86` [boolean]
Should we build an x86 image? Default: `true`

### `scan-image` [boolean]
Should the container image be scanned the security scanner? This step is non-blocking (but this may change in the future). Default: `true`

### `group-key` [string]
This is the key assigned to the job group that encapsulates the build tasks. This key is used by subsequent jobs that depend this build completing. Default: `build-and-push`

### `always-pull` [boolean]
Should the builder always attempt to pull fresh source images. This will ensure it always uses the latest available version of an image tag. Can be disabled to potentially improve build times _slightly_ if there is low risk of the upstream tagged image being updated. Default: `true`

### `composer-cache` [boolean]
Attempt to utilize a buildkite-cached composer package cache (_not_ a cache of `vendor`) when building the image. The cache **_must_** be available at `.composer-cache`. The cache will be made available as a build context called `composer-cache` (see [utilising-package-caches](#utilising-package-caches) for how to take advantag of this in your builds). If the image builds successfully the cache will be resaved at `pipeline` level so it can be reused as a base even if the manifest changes. See the [buildkite cache plugin](https://github.com/buildkite-plugins/cache-buildkite-plugin) for further details of how this works. Default: `false`

#### example
```yaml
  - label: cache-composer-deps
    command: |
      composer config -g github-oauth.github.com $${GITHUB_TOKEN};
      composer config -g cache-dir ./.composer-cache;
      composer install --download-only;
    plugins:
      - docker#v5.6.0:
          image: "362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/php-base:8.1-fpm-buster"
          always-pull: true
          mount-ssh-agent: true
          propagate-environment: true
          environment:
            - GITHUB_TOKEN
      - cache#v0.6.0:
          backend: s3
          manifest: composer.lock
          path: .composer-cache
          save: file
          restore: pipeline
  - label: ":docker: Build and upload container to ECR"
    branches: testing master
    plugins:
      - ssh://git@github.com/CatchoftheDay/build-and-push-buildkite-plugin.git#v1.2.0:
          composer-cache: true
```

### `npm-cache` [boolean]
Attempt to utilize a buildkite-cached npm package cache (_not_ a cache of `node_modules`) when building the image. The cache **_must_** be available at `.npm-cache`. The cache will be made available as a build-context called `npm-cache` (see [utilising-package-caches](#utilising-package-caches) for how to take advantag of this in your builds). If the image builds successfully the cache will be resaved at `pipeline` level so it can be reused as a base even if the manifest changes. See the [buildkite cache plugin](https://github.com/buildkite-plugins/cache-buildkite-plugin) for further details of how this works. Default: `false`

#### example
```yaml
  - label: cache-node-deps
    command: |
      echo "//npm.pkg.github.com/:_authToken=$${GITHUB_TOKEN}" > ~/.npmrc;
      npm config set -g cache ./.npm-cache;
      npm ci;
    plugins:
      - docker#v5.6.0:
          image: "362995399210.dkr.ecr.ap-southeast-2.amazonaws.com/catch/node-base:18-buster-slim"
          always-pull: true
          mount-ssh-agent: true
          propagate-environment: true
          environment:
            - GITHUB_TOKEN
      - cache#v0.6.0:
          backend: s3
          manifest: package-lock.json
          path: .npm-cache
          save: file
          restore: pipeline
  - label: ":docker: Build and upload container to ECR"
    branches: testing master
    plugins:
      - ssh://git@github.com/CatchoftheDay/build-and-push-buildkite-plugin.git#v1.2.0:
          npm-cache: true
```

## Utilising package caches

Only including the `composer-cache: true` or `npm-cache: true` flags isn't sufficient to take advantage of your package cache. The projects Dockerfile will also need to contain something like the following when performing the install step with the package manager.

#### composer

```Dockerfile
RUN --mount=type=cache,from=composer-cache,target=/root/.cache/composer \
    set -ex && \
    composer install \
        --no-scripts \
        --no-progress \
        --no-suggest \
        --prefer-dist \
        --no-dev \
        --no-autoloader \
        --no-interaction
```

#### npm

```Dockerfile
RUN --mount=type=cache,from=npm-cache,target=/root/.npm \
    set -ex && \
    npm ci
```

This will ensure that package files are picked up from the cache rather than being redownloaded from the internet.
