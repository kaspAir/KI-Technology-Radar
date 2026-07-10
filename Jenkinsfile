// Jenkins-Pipeline für den KI-Technology-Radar (Kern).
// Umsetzung des Suite-Testkonzepts (Zielarchitektur V0.1):
//  - Bei JEDEM Build läuft die schnelle deterministische Suite + Protokoll (Kap. 9/12, ADR-T06).
//  - Schwere Suiten (Systemintegration, Performance, dyn. Sicherheit) NUR auf int (ADR-T02).
//  - Smoke/Health auf int und prod; kein Testbetrieb in prod (Kap. 17).
//  - Deploy je Branch in die zugehörige Umgebung (Promotion dev -> test -> int -> main/prod).
//
// Branch  ->  Umgebung  ->  URL
//   dev   ->    dev      ->  https://dev.ki-tech-radar.ch
//   test  ->    test     ->  http://test.ki-tech-radar.ch
//   int   ->    int      ->  https://int.ki-tech-radar.ch
//   main  ->    prod     ->  https://ki-tech-radar.ch
//
// TODO (Infrastruktur, vom Betreiber zu ergänzen): Deploy-Mechanismus und
// Zielhosts. Hier NICHT geraten — die Deploy-Schritte sind Platzhalter mit
// klar markierten Einsprungpunkten und einer Jenkins-Credential 'ki-tech-radar-deploy'.

pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '30'))
  }

  environment {
    RADAR_ENV = "${env.BRANCH_NAME == 'main' ? 'prod' : (['dev','test','int'].contains(env.BRANCH_NAME) ? env.BRANCH_NAME : 'dev')}"
  }

  stages {
    stage('Info') {
      steps {
        echo "Branch=${env.BRANCH_NAME}  ->  Umgebung=${RADAR_ENV}"
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
        sh '''
          docker run --rm -v "$PWD/testing/protocols:/app/testing/protocols" \
            ki-tech-radar-test:${BUILD_NUMBER} \
            python testing/run_suite.py --env ${RADAR_ENV} --instance examples/sample-instance
        '''
      }
    }

    // Schwere Suiten laufen NUR auf int (Testart folgt Umgebungstreue, ADR-T02).
    // int Phase 1: interne Validierung gegen echte Umsysteme, vor Kundenzugriff (Kap. 7).
    stage('Schwere Suiten (int Phase 1)') {
      when { branch 'int' }
      steps {
        echo 'TODO int-Phase-1: Systemintegration (echte Umsysteme), Performance/Last, dynamische Sicherheit (DAST/Pentest).'
        echo 'Gegen die Integrationsumgebungen der Umsysteme; Lastfenster gegen Kundenbetrieb entkoppeln (Kap. 7).'
        echo 'Ergebnis fliesst in dasselbe Protokoll; interne Freigabe (Signatur) ist das Tor zu Phase 2.'
      }
    }

    // Smoke/Health: nicht-destruktiv, auf int und prod (Kap. 4/17).
    stage('Smoke / Health') {
      when { anyOf { branch 'int'; branch 'main' } }
      steps {
        echo "TODO Smoke/Health-Check gegen Umgebung ${RADAR_ENV} (nicht-destruktiv)."
      }
    }

    // Deploy je Branch in die zugehörige Umgebung. dev/test sind gesetzt,
    // int/prod-URLs noch offen. Deploy-Mechanismus/Host: vom Betreiber zu ergänzen.
    stage('Deploy') {
      steps {
        script {
          def targets = [
            dev : 'https://dev.ki-tech-radar.ch',
            test: 'http://test.ki-tech-radar.ch',
            int : 'https://int.ki-tech-radar.ch',
            prod: 'https://ki-tech-radar.ch',
          ]
          echo "Deploy nach ${RADAR_ENV}: ${targets[RADAR_ENV]}"
          // TODO Betreiber: hier den tatsächlichen Deploy einhängen (z.B. SSH-git-pull
          // wie im Suite-Stack üblich), Credential-ID 'ki-tech-radar-deploy'.
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
