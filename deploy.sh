#!/usr/bin/env bash
#
# Deploys Iris to Google App Engine, setting up Roles, Sinks, Topics, and Subscriptions as needed.
# Usage
# - Pass the project as the first command line argument.
# - Options -p -o -c as documented in usage (try -h)
# - Optionally set environment variable GAEVERSION to set the Google App Engine Version.
#

set -x
set -u
set -e

SHELL_DETECTION=$(ps -p $$ -oargs= )

if [[ ! "$SHELL_DETECTION" == *bash* ]]; then
  echo >&2 "Need Bash. Found \"$SHELL_DETECTION\""
  exit 1
else
  echo ""
fi

if [[ "$BASH_VERSION" == 3. ]]; then
  echo >&2 "Need Bash version 4 and up. Now $BASH_VERSION"
  exit 1
fi

export PYTHONPATH="."
python3 ./util/check_python_version.py

pip3 install -r requirements.txt

START=$(date "+%s")

export LOGS_TOPIC=iris_logs_topic

if [[ $# -eq 0 ]]; then
  echo Missing project id argument. Run with --help switch for usage.
  exit
fi

export PROJECT_ID=$1

shift
deploy_proj=
deploy_org=
export CRON_ONLY=
while getopts 'cpo' opt; do
  case $opt in
  c)
    export CRON_ONLY=true
    ;;
  p)
    deploy_proj=true
    ;;
  o)
    deploy_org=true
    ;;
  *)
    cat <<EOF
      Usage deploy.sh PROJECT_ID [-c]
          Argument:
                  The project to which Iris 3 will be deployed
          Options, to be given at end of line, after project ID.
            If neither -p nor -o is given, this is treated as the default, -p -o (i.e., do both):
                  -p: Deploy Iris (to the project given by the arg)
                  -o: Set up org-level elements like Log Sink
                  -c: Use only Cloud Scheduler cron to add labels; do not add labels on resource creation.
                  If you are changing to be Cloud-Scheduler-only with -c or not Cloud_Scheduler-only
                  without -c, be sure to run both org and project deployments.
                  (To *not at all* use Cloud Scheduler, delete the schedule in `cron.yaml`.)
          Environment variable:
                  GAEVERSION (Optional) sets the Google App Engine Version.
EOF
    exit 1
    ;;
  esac
done

if [[ "$deploy_org" != "true" ]] && [[ "$deploy_proj" != "true" ]]; then
  deploy_org=true
  deploy_proj=true
  echo >&2 "Default option: Deploy project and also org"
fi


gcloud projects describe "$PROJECT_ID" || {
  echo "Project $PROJECT_ID not found"
  exit 1
}

echo "Project ID $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

GAE_SVC=$(grep "service:" app.yaml | awk '{print $2}')
# This dependson the  the export PYTHON_PATH="." above.
PUBSUB_VERIFICATION_TOKEN=$(python3 ./util/print_pubsub_token.py)
LABEL_ONE_SUBSCRIPTION_ENDPOINT="https://${GAE_SVC}-dot-${PROJECT_ID}.${GAE_REGION_ABBREV}.r.appspot.com/label_one?token=${PUBSUB_VERIFICATION_TOKEN}"
DO_LABEL_SUBSCRIPTION_ENDPOINT="https://${GAE_SVC}-dot-${PROJECT_ID}.${GAE_REGION_ABBREV}.r.appspot.com/do_label?token=${PUBSUB_VERIFICATION_TOKEN}"

declare -A enabled_services
while read -r svc _; do
  # Using the associative array as a set. The value does not matter, just that we can check that a key is in it.
  enabled_services["$svc"]=yes
done < <(gcloud services list | tail -n +2)

required_svcs=(
  cloudscheduler.googleapis.com
  cloudresourcemanager.googleapis.com
  pubsub.googleapis.com
  compute.googleapis.com
  bigtable.googleapis.com
  bigtableadmin.googleapis.com
  storage-component.googleapis.com
  sql-component.googleapis.com
  sqladmin.googleapis.com
)
for svc in "${required_svcs[@]}"; do
  if ! [ ${enabled_services["$svc"]+_} ]; then
    gcloud services enable "$svc"
  fi
done

# Get organization id for this project
ORGID=$(curl -X POST -H "Authorization: Bearer \"$(gcloud auth print-access-token)\"" \
  -H "Content-Type: application/json; charset=utf-8" \
  https://cloudresourcemanager.googleapis.com/v1/projects/"${PROJECT_ID}":getAncestry | grep -A 1 organization |
  tail -n 1 | tr -d ' ' | cut -d'"' -f4)

# Create App Engine app
gcloud app describe >&/dev/null || gcloud app create --region=$REGION

# Create custom role to run iris
if gcloud iam roles describe "$ROLEID" --organization "$ORGID"; then
  gcloud iam roles update -q "$ROLEID" --organization "$ORGID" --file roles.yaml
else
  gcloud iam roles create "$ROLEID" -q --organization "$ORGID" --file roles.yaml
fi

if [[ "$deploy_proj" == "true" ]]; then
  ./scripts/_deploy-project.sh
fi

FINISH=$(date "+%s")
ELAPSED_SEC=$((FINISH - START))
echo >&2 "Elapsed time for $(basename "$0") ${ELAPSED_SEC} s"
