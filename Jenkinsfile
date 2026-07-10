// Jenkins-Pipeline für den KI-Technology-Radar (Kern).
// Umsetzung des Suite-Testkonzepts (Zielarchitektur V0.1):
//  - Bei JEDEM Build läuft die schnelle deterministische Suite + Protokoll (Kap. 9/12, ADR-T06).
//  - Schwere Suiten (Systemintegration, Performance, dyn. Sicherheit) NUR auf int (ADR-T02).
//  - Smoke/Health auf int und prod; kein Testbetrieb in prod (Kap. 17).
//  - Deploy je Branch in die zugehörige Umgebung (Promotion dev -> test -> int -> main/prod).
//
// Branch  ->  Umgebung  ->  URL                         ->  Jenkins-Job
//   dev   ->    dev      ->  https://dev.ki-tech-radar.ch    3.1 KI-Radar dev
//   test  ->    test     ->  http://test.ki-tech-radar.ch    3.2 KI-Radar Test
//   int   ->    int      ->  https://int.ki-tech-radar.ch    3.3 KI-Radar Int
//   main  ->    prod     ->  https://ki-tech-radar.ch        3.4 KI-Radar Prod
//
// Setup: vier SEPARATE Single-Branch-Jobs (kein Multibranch). Deshalb wird die
// Umgebung NICHT aus BRANCH_NAME abgeleitet (das gibt es nur in Multibranch),
// sondern aus dem tatsächlich ausgecheckten Branch (checkout scm -> GIT_BRANCH).
// Override möglich über ein Job-Environment RADAR_ENV (dev|test|int|prod).
//
// TODO (Infrastruktur, vom Betreiber): realer Deploy-Mechanismus + Zielhosts,
// Jenkins-Credential 'ki-tech-radar-deploy'. Hier NICHT geraten.

pipeline {
  agent any

  options {
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '30'))
  }

  stages {
    stage('Setup') {
      steps {
        script {
          def scmVars = checkout scm
          def branch = (scmVars.GIT_BRANCH ?: '').replaceAll('^origin/', '')
          def mapping = [dev: 'dev', test: 'test', int: 'int', main: 'prod']
          // 1. bekannter Branch gewinnt; 2. sonst Job-Override RADAR_ENV; 3. sonst dev.
          env.RADAR_ENV = mapping.get(branch, (env.RADAR_ENV ?: 'dev'))
          // Commit fuer die Herkunft im Testprotokoll (Container hat kein git).
          env.RADAR_COMMIT = scmVars.GIT_COMMIT ?: ''
          echo "Branch=${branch}  ->  Umgebung=${env.RADAR_ENV}  (Commit ${env.RADAR_COMMIT})"
        }
      }
    }

    // Reproduzierbares Testimage (Ausführung: Docker).
    stage('Build Testimage') {
      steps {
        sh 'docker build -t ki-tech-radar-test:${BUILD_NUMBER} .'
      }
    }

    // Schnelle deterministische Suite bei JEDEM Build (dev/test/int).
    // Enthält pytest (Unit/Kontrakt), validate.py (Schema/Integrität) und
    // statische Sicherheit. Erzeugt das versionierte Testprotokoll.
    stage('Schnelle Suite + Protokoll') {
      steps {
        // Kein Bind-Mount: unter Docker-outside-of-Docker zeigt -v auf den
        // Daemon-Host, nicht in den Workspace. Protokoll per 'docker cp' holen.
        sh '''
          docker run --name radar-suite-${BUILD_NUMBER} -e RADAR_COMMIT="${RADAR_COMMIT}" \
            ki-tech-radar-test:${BUILD_NUMBER} \
            python testing/run_suite.py --env ${RADAR_ENV} --instance examples/sample-instance
          code=$?
          mkdir -p testing/protocols
          docker cp radar-suite-${BUILD_NUMBER}:/app/testing/protocols/. testing/protocols/ || true
          docker rm radar-suite-${BUILD_NUMBER} >/dev/null 2>&1 || true
          exit $code
        '''
      }
    }

    // Schwere Suiten laufen NUR auf int (Testart folgt Umgebungstreue, ADR-T02).
    // int Phase 1: interne Validierung gegen echte Umsysteme, vor Kundenzugriff (Kap. 7).
    stage('Schwere Suiten (int Phase 1)') {
      when { expression { env.RADAR_ENV == 'int' } }
      steps {
        echo 'TODO int-Phase-1: Systemintegration (echte Umsysteme), Performance/Last, dynamische Sicherheit (DAST/Pentest).'
        echo 'Gegen die Integrationsumgebungen der Umsysteme; Lastfenster gegen Kundenbetrieb entkoppeln (Kap. 7).'
        echo 'Ergebnis fliesst in dasselbe Protokoll; interne Freigabe (Signatur) ist das Tor zu Phase 2.'
      }
    }

    // Smoke/Health: nicht-destruktiv, auf int und prod (Kap. 4/17).
    stage('Smoke / Health') {
      when { expression { env.RADAR_ENV == 'int' || env.RADAR_ENV == 'prod' } }
      steps {
        echo "TODO Smoke/Health-Check gegen Umgebung ${env.RADAR_ENV} (nicht-destruktiv)."
      }
    }

    // Deploy je Umgebung. dev/test/int/prod-URLs sind gesetzt; der Deploy-
    // Mechanismus/Host ist vom Betreiber zu ergänzen (nicht geraten).
    stage('Deploy') {
      steps {
        script {
          def targets = [
            dev : 'https://dev.ki-tech-radar.ch',
            test: 'http://test.ki-tech-radar.ch',
            int : 'https://int.ki-tech-radar.ch',
            prod: 'https://ki-tech-radar.ch',
          ]
          echo "Deploy nach ${env.RADAR_ENV}: ${targets[env.RADAR_ENV]}"
          // TODO Betreiber: hier den tatsächlichen Deploy einhängen (z.B. SSH-git-pull),
          // Credential-ID 'ki-tech-radar-deploy'.
          // withCredentials([...]) { sh 'deploy ...' }
          echo 'TODO: Deploy-Schritt noch nicht konfiguriert (keine Infrastruktur geraten).'
        }
      }
    }
  }

  post {
    always {
      // Testprotokoll als auditierbares Build-Artefakt sichern (Kap. 12).
      archiveArtifacts artifacts: 'testing/protocols/*.yaml', allowEmptyArchive: true, fingerprint: true
    }
  }
}
