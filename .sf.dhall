let Zuul =
        env:DHALL_ZUUL
      ? https://raw.githubusercontent.com/softwarefactory-project/dhall-zuul/0.2.0/package.dhall sha256:d5c755bd75834d9853994a043e98f04b2e31585222048b6ca0036f1bbf7fd7f0

let Prelude =
        env:DHALL_PRELUDE
      ? https://raw.githubusercontent.com/dhall-lang/dhall-lang/v17.0.0/Prelude/package.dhall sha256:10db3c919c25e9046833df897a8ffe2701dc390fa0893d958c3430524be5a43e

let pyjob = Zuul.Job::{ nodeset = Some (Zuul.Nodeset.Name "python-latest-pod") }

let docjob =
          pyjob
      //  { vars = Some
              (Zuul.Vars.mapText (toMap { sphinx_build_dir = "build" }))
          }

let jobs =
      [ Zuul.Job.Name "shake-factory-test"
      , Zuul.Job.WithOptions docjob "tox-docs"
      , Zuul.Job.WithOptions pyjob "tox-linters"
      , Zuul.Job.WithOptions pyjob "tox-py36"
      ]

let {- rpm-check adds the sf-rpm-build job for check pipeline
    -} rpm-check =
      \(jobs : List Zuul.Job.union) ->
        Zuul.ProjectPipeline::{ jobs = [ Zuul.Job.Name "sf-rpm-build" ] # jobs }

let {- rpm-gate adds the sf-rpm-build and sf-rpm-publish jobs for gate pipeline.
       The sf-rpm-publish automatically depends on all the defined jobs.
    -}
    rpm-gate =
      \(jobs : List Zuul.Job.union) ->
        let jobs = [ Zuul.Job.Name "sf-rpm-build" ] # jobs

        in  Zuul.ProjectPipeline::{
            , jobs =
                  [ Zuul.Job.WithOptions
                      Zuul.Job::{
                      , dependencies = Some
                          ( Prelude.List.map
                              Text
                              Zuul.Job.Dependency.union
                              Zuul.Job.Dependency.Name
                              ( Prelude.List.map
                                  Zuul.Job.union
                                  Text
                                  Zuul.Job.getUnionName
                                  jobs
                              )
                          )
                      }
                      "sf-rpm-publish"
                  ]
                # jobs
            }

let pipelines =
      toMap
        { check = rpm-check jobs
        , gate = rpm-gate jobs
        , post = Zuul.ProjectPipeline.mkSimple [ "shake-factory-publish-docs" ]
        , release =
            Zuul.ProjectPipeline.mkSimple [ "sf-rpm-publish", "upload-pypi" ]
        }

in  { zuul = Zuul.Project.wrap [ Zuul.Project.Pipelines pipelines ] }
