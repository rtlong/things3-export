{
  inputs = {
    nixpkgs.url = "github:cachix/devenv-nixpkgs/rolling";
    systems.url = "github:nix-systems/default";

    devenv.url = "github:cachix/devenv";
    devenv.inputs.nixpkgs.follows = "nixpkgs";

    nixpkgs-python.url = "github:cachix/nixpkgs-python";
    nixpkgs-python.inputs = { nixpkgs.follows = "nixpkgs"; };
  };

  nixConfig = {
    extra-trusted-public-keys = "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZLr6cv/Hm9XgU50cw=";
    extra-substituters = "https://devenv.cachix.org";
  };

  outputs = { self, nixpkgs, devenv, systems, ... } @ inputs:
    let
      forEachSystem = nixpkgs.lib.genAttrs (import systems);
    in
    {
      packages = forEachSystem (system: {
        devenv-up = self.devShells.${system}.default.config.procfileScript;
        devenv-test = self.devShells.${system}.default.config.test;
      });

      devShells = forEachSystem
        (system:
          let
            pkgs = nixpkgs.legacyPackages.${system};
          in
          {
            default = devenv.lib.mkShell {
              inherit inputs pkgs;
              modules = [
                {
                  # https://devenv.sh/reference/options/
                  packages = with pkgs;[
                    cmake
                  ];

                  # enterShell = ''
                  # '';

                  languages.python = {
                    enable = true;

                    venv.enable = true;

                    # NOTE: when initially getting this running on mac with apple silicon: comment this line out, allow the dev shell to succeed, then in that shell run the following to install pytorch before uncommenting this: `pip3 install --pre torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/nightly/cpu`
                    # venv.requirements = ./requirements.txt;

                    version = "3.11";
                  };
                }
              ];
            };
          });
    };
}
