let Zuul =
        env:DHALL_ZUUL
      ? https://raw.githubusercontent.com/softwarefactory-project/dhall-zuul/0.1.0/package.dhall sha256:40c8a33ee920d12ac4b27571031e27722b4ef63771abaaaca471bc08654c31dc

let Prelude =
        env:DHALL_PRELUDE
      ? https://raw.githubusercontent.com/dhall-lang/dhall-lang/v17.0.0/Prelude/package.dhall sha256:10db3c919c25e9046833df897a8ffe2701dc390fa0893d958c3430524be5a43e

let python-job =
      Zuul.Job.WithOptions
        Zuul.Job::{ nodeset = Some (Zuul.Nodeset.Name "python-latest-pod") }

let jobs =
      [ Zuul.Job.Name "shake-factory-test"
      , python-job "tox-docs"
      , python-job "tox-linters"
      , python-job "tox-py36"
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
        }

in  { zuul = Zuul.Project.wrap [ Zuul.Project.Pipelines pipelines ] }
