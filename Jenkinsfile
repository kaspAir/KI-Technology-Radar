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
// Deploy: rsync der statischen Seite über SSH via deploy/deploy.sh (SSH-basiert
// wie die übrige Suite), scharf nur bei DEPLOY_ENABLED=true. Host/Pfade/Credential
// kommen aus Jenkins-Env/Credentials (siehe deploy/README.md) — nichts geraten.

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
          echo "Deploy-Konfig: DEPLOY_HOST=${env.DEPLOY_HOST ? 'gesetzt' : 'FEHLT'}, " +
               "DEPLOY_CREDENTIAL=${env.DEPLOY_CREDENTIAL ?: '(default ki-tech-radar-deploy)'}, " +
               "DEPLOY_ENABLED=${env.DEPLOY_ENABLED ?: 'nicht gesetzt'}"
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

    // Einmalige Hilfe bei der Einrichtung: solange der Deploy nicht scharf ist,
    // aber DEPLOY_HOST gesetzt wurde, die Subdomain-Docroots am Host auflisten
    // (rein lesend). Sobald DEPLOY_ENABLED=true, wird diese Stage übersprungen.
    stage('Deploy-Ziel ermitteln') {
      when { expression { env.DEPLOY_ENABLED?.trim() != 'true' && env.DEPLOY_HOST?.trim() } }
      steps {
        sshagent(credentials: [(env.DEPLOY_CREDENTIAL?.trim() ?: 'ki-tech-radar-deploy')]) {
          sh '''
            ssh -o StrictHostKeyChecking=no "$DEPLOY_HOST" 'echo "HOME=$HOME"; echo "=== ~/sites ==="; ls -1 ~/sites 2>/dev/null; echo "=== Kandidaten (ki-tech-radar) ==="; find ~ -maxdepth 4 -iname "*ki-tech-radar*" 2>/dev/null'
          '''
        }
      }
    }

    // Deploy je Umgebung: rsync von site/ in den Docroot (deploy/deploy.sh). Läuft
    // nur scharf bei DEPLOY_ENABLED=true — sonst sauber übersprungen, Build bleibt
    // grün. Nur der öffentliche Kern wird deployt, nie die private Instanz.
    stage('Deploy') {
      when { expression { env.DEPLOY_ENABLED?.trim() == 'true' } }
      steps {
        sshagent(credentials: [(env.DEPLOY_CREDENTIAL?.trim() ?: 'ki-tech-radar-deploy')]) {
          sh '''
            export SSH_OPTS="-o StrictHostKeyChecking=no"
            bash deploy/deploy.sh
          '''
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
