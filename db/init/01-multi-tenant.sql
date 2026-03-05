-- Multi-tenant bootstrap: create platform DB and grant privileges.
-- Runs automatically on first MariaDB boot (empty data volume only).
-- The MYSQL_USER ('berengario') has already been created by the official
-- MariaDB entrypoint before this script executes.

CREATE DATABASE IF NOT EXISTS `berengario_platform`;
GRANT ALL PRIVILEGES ON `berengario_platform`.* TO 'berengario'@'%';
GRANT ALL PRIVILEGES ON `berengario_tenant_%`.* TO 'berengario'@'%';
GRANT CREATE ON *.* TO 'berengario'@'%';
FLUSH PRIVILEGES;
