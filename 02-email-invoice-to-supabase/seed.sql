-- Datos de siembra de 02-email-invoice-to-supabase (Andes Freight).
-- Negocio y datos ficticios. Son los dos catalogos contra los que el workflow
-- controla cada factura: el proveedor con su moneda esperada y la orden de
-- compra con su monto. Sin estas filas no hay contra que comparar.
-- Cargado y verificado el 18/10/2026 contra el Postgres local (ver ../local/).

insert into proveedores (nombre, moneda_esperada) values
  ('Combustibles del Litoral SA', 'ARS'),
  ('Repuestos Andinos SRL', 'ARS'),
  ('Global Reefer Parts Inc', 'USD')
on conflict (nombre) do nothing;

insert into ordenes_compra (numero_oc, proveedor, monto, moneda, estado) values
  ('OC-2026-0441', 'Combustibles del Litoral SA', 185000, 'ARS', 'abierta'),
  ('OC-2026-0442', 'Repuestos Andinos SRL', 62000, 'ARS', 'abierta'),
  ('OC-2026-0443', 'Global Reefer Parts Inc', 4200, 'USD', 'abierta')
on conflict (numero_oc) do nothing;
