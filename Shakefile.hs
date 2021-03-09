-- Interpret using this command:
--    podman run -it --rm -v $(pwd):/data:Z quay.io/software-factory/shake-factory
--
-- Learn more at: https://softwarefactory-project.io/cgit/software-factory/shake-factory/tree/README.md

import Control.Monad (unless)
import Development.Shake
import ShakeFactory
import ShakeFactory.Dhall

buildDocs :: Action ()
buildDocs =
  do
    pdoc3 <- ensurePdoc3
    args <- getCmdFromTox
    putInfo $ "args: " <> args
    cmd_ "rm -Rf build/docs"
    cmd_ pdoc3 args
    cmd_ "mv build/html/pynotedb build/docs"
  where
    -- Returns the pdoc3 args from the tox.ini file
    getCmdFromTox = do
      tox <- readFileLines "tox.ini"
      let toxs = map words tox
      let cmd = [x | x@("commands" : "=" : "pdoc3" : _) <- toxs]
      let args = map (dropWhile (/= "pdoc3")) cmd
      pure (head (map (unwords . drop 1) args))
    -- Ensures pdoc3 is installed and returns its path
    ensurePdoc3 = do
      home <- getEnvWithDefault "/home/user" "HOME"
      let pdoc3 = home <> "/.local/bin/pdoc3"
      pdoc3Installed <- doesFileExist pdoc3
      unless pdoc3Installed (cmd_ "pip3 install --user pdoc3")
      pure pdoc3

main :: IO ()
main = shakeMain $ phony "docs" buildDocs
