# build-and-push-buildkite-plugin

A concise plugin to assist with build multi-arch container images and pushing them to an ECR repository.

Subsequent pipeline steps can `depend_on` the step key: `build-and-push` to ensure that image building and pushing is complete before continuing (see [`group-key`](#group-key-string) for configuring this value).

## Usage
```yaml
steps:
  - plugins:
    - ssh://git@github.com/CatchoftheDay/build-and-push-buildkite-plugin.git#v0.0.6: ~
```

## Configuration
All configuration is optional.

```yaml
steps:
  - plugins:
    - ssh://git@github.com/CatchoftheDay/build-and-push-buildkite-plugin.git#v0.0.6:
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

### `build-arm` [boolean]
Should we build an ARM image? Default: `true`

### `build-x86` [boolean]
Should we build an x86 image? Default: `true`

### `scan-image` [boolean]
Should the container image be scanned with the Rapid 7 scanner? This step is non-blocking (but this may change in the future). Default: `true`

### `group-key` [string]
This is the key assigned to the job group that encapsulates the build tasks. This key is used by subsequent jobs that depend this build completing. Default: `build-and-push`
