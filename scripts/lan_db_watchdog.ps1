while ($true) {
  docker exec ndga-db-1 psql -U ndga -d postgres -c "select pg_terminate_backend(pid) from pg_stat_activity where usename='ndga' and pid <> pg_backend_pid() and state in ('idle','idle in transaction') and now() - state_change > interval '20 seconds';" | Out-Null
  Start-Sleep -Seconds 10
}
