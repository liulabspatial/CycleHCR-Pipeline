
# This is based on https://github.com/apache/spark-docker/blob/master/entrypoint.sh.template
attempt_setup_fake_passwd_entry() {
  # Check whether there is a passwd entry for the container UID
  local myuid; myuid="$(id -u)"
  # If there is no passwd entry for the container UID, attempt to fake one
  # You can also refer to the https://github.com/docker-library/official-images/pull/13089#issuecomment-1534706523
  # It's to resolve OpenShift random UID case.
  # See also: https://github.com/docker-library/postgres/pull/448
  if ! getent passwd "$myuid" &> /dev/null; then
      local wrapper
      for wrapper in {/usr,}/lib{/*,}/libnss_wrapper.so; do
        if [ -s "$wrapper" ]; then
          NSS_WRAPPER_PASSWD="$(mktemp)"
          NSS_WRAPPER_GROUP="$(mktemp)"
          export LD_PRELOAD="$wrapper" NSS_WRAPPER_PASSWD NSS_WRAPPER_GROUP
          local mygid; mygid="$(id -g)"
          printf 'spark:x:%s:%s:${SPARK_USER_NAME:-anonymous uid}:%s:/bin/false\n' "$myuid" "$mygid" "$SPARK_HOME" > "$NSS_WRAPPER_PASSWD"
          printf 'spark:x:%s:\n' "$mygid" > "$NSS_WRAPPER_GROUP"
          break
        fi
      done
  fi
}

switch_user_if_root() {
  if [ $(id -u) -eq 0 ]; then
    echo gosu spark
  fi
}

umask 0002
