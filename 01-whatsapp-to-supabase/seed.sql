-- Datos de siembra de 01-whatsapp-to-supabase (NortePeak).
-- Negocio y datos ficticios. Son los catalogos que el workflow lee antes de
-- juzgar un lead: la zona de cobertura y los vendedores. Sin estas filas el
-- flujo no puede decidir nada, asi que van versionadas al lado del esquema.
-- Cargado y verificado el 18/10/2026 contra el Postgres local (ver ../local/).

insert into zonas_cobertura (ciudad, cobertura, vendedor_default) values
  ('San Miguel de Tucumán', true, 'Marina Ponce'),
  ('Yerba Buena', true, 'Marina Ponce'),
  ('Tafí Viejo', true, 'Ezequiel Soler'),
  ('Santiago del Estero', false, null)
on conflict (ciudad) do nothing;

insert into vendedores (nombre, zona, activo, carga_actual) values
  ('Marina Ponce', 'San Miguel de Tucumán / Yerba Buena', true, 3),
  ('Ezequiel Soler', 'Tafí Viejo', true, 1)
on conflict (nombre) do nothing;
