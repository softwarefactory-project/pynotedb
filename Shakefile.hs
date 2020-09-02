-- Interpret using this command:
--    podman run -it --rm -v $(pwd):/data:Z quay.io/software-factory/shake-factory
--
-- Learn more at: https://softwarefactory-project.io/cgit/software-factory/shake-factory/tree/README.md

import Development.Shake
import ShakeFactory
import ShakeFactory.Dhall

main = shakeMain $ do
  want $ [".zuul.yaml"]
  ".zuul.yaml" %> dhallZuulAction "(./.sf.dhall).zuul"
  phony "docs" $ do
    cmd_ "rm -Rf build/docs"
    cmd_ "tox -edocs"
    cmd_ "mv build/pdoc/pynotedb build/docs"
