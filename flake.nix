{
  inputs = {
    nixpkgs.url = "https://flakehub.com/f/DeterminateSystems/nixpkgs-weekly/0.tar.gz";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            python3
            uv
            ruff
            basedpyright
          ];

          shellHook = ''
            export UV_PYTHON_DOWNLOADS=never
            export UV_PYTHON="$(command -v python)"
            export UV_PROJECT_ENVIRONMENT="$PWD/.venv"

            if [ ! -d "$UV_PROJECT_ENVIRONMENT" ]; then
              uv venv --python "$UV_PYTHON" "$UV_PROJECT_ENVIRONMENT" >/dev/null
            fi

            . "$UV_PROJECT_ENVIRONMENT/bin/activate"
          '';
        };
      }
    );
}
