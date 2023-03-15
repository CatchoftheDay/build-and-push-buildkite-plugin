# build-and-push-buildkite-plugin

A concise plugin to assist with build multi-arch container images and pushing them to an ECR repository.

Subsequent pipeline steps can `depend_on` the step key: `build-and-push` to ensure that image building and pushing is complete before continuing.

## Usage
```yaml
steps:
  - plugins:
    - ssh://git@github.com/CatchoftheDay/build-and-push-buildkite-plugin.git#<PLUGIN TAG>: ~

```

## Configuration
All configuration is optional.

```yaml
steps:
  - plugins:
    - ssh://git@github.com/CatchoftheDay/build-and-push-buildkite-plugin.git#v<PLUGIN TAG>:
        dockerfile: Dockerfile
        dockerfile-path: "."
        image-name: my-super-special-application
        image-tag: latest
        build-args: "secret-from-vault,not-a-secret=42"
        build-arm: true
        build-x86: true
        scan-image: true
```

`dockerfile` [string]:
The name of the Dockerfile to build. Default: `Dockerfile`

`dockerfile-path` [string]:
A path relative to the repository root directory to find the Dockerfile. Default: `.`

`image-name` [string]:
The name of your application image. Will be prefixed with `catch/` before being pushed to the registry. Default: Buildkite pipeline name (`$BUILDKITE_PIPELINE_NAME`).

`image-tag` [string]:
A container image tag. Default: First 10 characters of git SHA.

`build-args` [comma-delimited list]: Additional build-arguments (`--build-arg`) to pass to `docker build`. These can be single values (ideally used for secrets that are available to every pipeline step as env vars) or key=value pairs which can be used to pass in non-secret values that aren't known to every step of the pipeline. Default: `""`, `GITHUB_TOKEN` is always provided.

`build-arm` [boolean]: Should we build an ARM image? Default: `true`

`build-x86` [boolean]: Should we build an x86 image? Default: `true`

`scan-image` [boolean]: Should the container image be scanned with the Rapid 7 scanner? This step is non-blocking (but this may change in the future). Default: `true`
