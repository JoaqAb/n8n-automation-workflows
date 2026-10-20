-- Esquema de Supabase para 02-email-invoice-to-supabase (Andes Freight)
-- Caso self-initiated de portfolio. Negocio y datos ficticios.
-- Ver ../../README.md y docs/portfolio/N8N_CASES.md (lokebox-landing) para el contexto completo.

create extension if not exists pgcrypto;

-- Catálogo simple de proveedores, con la moneda esperada de cada uno.
-- Existe específicamente para el edge case de "moneda distinta a la
-- esperada": sin este catálogo no hay contra qué comparar.
create table proveedores (
  nombre text primary key,
  moneda_esperada text not null default 'ARS' check (moneda_esperada in ('ARS', 'USD'))
);

-- Órdenes de compra. Una factura sin OC asociada, o con monto que no
-- coincide, es una excepción explícita (ver tabla facturas), nunca un
-- supuesto silencioso.
create table ordenes_compra (
  id uuid primary key default gen_random_uuid(),
  numero_oc text unique not null,
  proveedor text not null references proveedores(nombre),
  monto numeric not null,
  moneda text not null check (moneda in ('ARS', 'USD')),
  fecha timestamptz not null default now(),
  estado text not null default 'abierta' check (estado in ('abierta', 'cerrada'))
);

-- Tabla principal. Mismo criterio que `leads` en el caso 01: una sola
-- columna de estado con un check que enumera todos los estados de
-- excepción como ciudadanos de primera clase, nunca una bandera booleana
-- aislada por tipo de problema.
create table facturas (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- origen: el email crudo nunca se descarta, igual que el payload crudo
  -- en leads (caso 01) y el mensaje original en bot/claude.js (lokebox-app)
  raw_email_subject text,
  raw_email_from text,
  raw_attachment_url text not null,

  -- extracción con IA
  proveedor text,
  numero_factura text,
  monto numeric,
  moneda text check (moneda in ('ARS', 'USD')),
  fecha_emision date,
  numero_oc text,
  lineas jsonb,
  confianza_extraccion numeric check (confianza_extraccion between 0 and 1),

  -- máquina de estados
  estado text not null default 'recibida' check (estado in (
    'recibida',
    'extraida',
    'duplicada',
    'excepcion_baja_confianza',
    'excepcion_sin_oc',
    'excepcion_monto',
    'excepcion_moneda',
    'pendiente_aprobacion',
    'aprobada',
    'rechazada',
    'conciliada'
  )),
  motivo_excepcion text,

  -- aprobación humana (cuando aplica, ver workflow-approval.json)
  aprobado_por text,
  aprobado_en timestamptz,
  conciliado_en timestamptz
);

-- Dedup: una factura se identifica como duplicada por proveedor + número
-- de factura (dos emails distintos de la misma factura, o un reenvío).
create unique index idx_facturas_proveedor_numero on facturas (proveedor, numero_factura)
  where estado not in ('rechazada', 'duplicada');

create index idx_facturas_estado on facturas (estado);

-- RLS: insert-only desde el rol que usa n8n para el intake, update acotado
-- a la máquina de estados (mismo patrón que leads en el caso 01).
alter table facturas enable row level security;

create policy "n8n puede insertar facturas"
  on facturas for insert
  to service_role
  with check (true);

create policy "n8n puede actualizar el propio flujo de estado"
  on facturas for update
  to service_role
  using (true);

-- Los datos de siembra (los catalogos que el workflow lee) viven en seed.sql,
-- al lado de este archivo. Se cargan despues de este esquema.
