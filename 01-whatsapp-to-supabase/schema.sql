-- Esquema de Supabase para 01-whatsapp-to-supabase (NortePeak)
-- Caso self-initiated de portfolio. Negocio y datos ficticios.
-- Ver ../../README.md y docs/portfolio/N8N_CASES.md (lokebox-landing) para el contexto completo.

create extension if not exists pgcrypto;

-- Catálogo de zonas de cobertura. Se consulta antes de calificar: un lead
-- fuera de zona nunca debería llegar a costarle tiempo a un vendedor.
create table zonas_cobertura (
  ciudad text primary key,
  cobertura boolean not null default true,
  vendedor_default text
);

-- Catálogo simple de vendedores, para el routing por zona/carga.
create table vendedores (
  nombre text primary key,
  zona text,
  activo boolean not null default true,
  carga_actual integer not null default 0
);

-- Tabla principal. El estado (`estado`) es la máquina de estados completa
-- del lead, incluye los estados de excepción (duplicado, fuera de zona,
-- dato faltante, revisión manual) como ciudadanos de primera clase, no como
-- casos especiales tratados aparte -- mismo criterio que "El Libro" en
-- lokebox-app: una sola fuente de verdad para el estado, nunca una bandera
-- booleana por excepción.
create table leads (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- origen: de dónde vino el lead, y el payload crudo para auditoría/debug
  -- (nunca se descarta el dato crudo aunque ya esté normalizado, mismo
  -- criterio que bot/claude.js en lokebox-app guarda el mensaje original)
  source text not null check (source in ('web_form', 'whatsapp')),
  raw_payload jsonb not null,

  -- datos normalizados (mismo shape sin importar el canal de origen)
  nombre text,
  telefono text not null,
  email text,
  direccion text,
  ciudad text,
  tipo_cliente text check (tipo_cliente in ('residencial', 'pyme')),
  consumo_declarado_kwh numeric,
  urgencia text check (urgencia in ('inmediata', 'este_mes', 'explorando')),

  -- máquina de estados
  estado text not null default 'nuevo' check (estado in (
    'nuevo',
    'duplicado',
    'fuera_de_zona',
    'dato_faltante',
    'revision_manual',
    'calificado',
    'asignado',
    'contactado',
    'cerrado'
  )),

  -- calificación por IA
  score_ia integer check (score_ia between 0 and 100),
  confianza_ia numeric check (confianza_ia between 0 and 1),
  presupuesto_estimado_rango text,
  motivo_revision_manual text,

  -- enrichment (geocoding de la dirección declarada)
  zona_cobertura boolean,
  lat numeric,
  lng numeric,

  -- routing y seguimiento
  vendedor_asignado text references vendedores(nombre),
  fecha_asignacion timestamptz,
  ultimo_contacto timestamptz,
  recordatorio_enviado_en timestamptz
);

-- Dedup: un lead se identifica como duplicado por teléfono dentro de una
-- ventana de 48hs (ver workflow, nodo "Check Duplicate"). El índice existe
-- para que esa consulta sea barata incluso con volumen.
create index idx_leads_telefono_created on leads (telefono, created_at desc);

create index idx_leads_estado on leads (estado);

-- RLS: insert-only desde el rol que usa n8n (mismo patrón que lead/visits
-- en lokebox-quote: el proceso de intake nunca necesita leer leads ajenos,
-- solo escribir el propio).
alter table leads enable row level security;

create policy "n8n puede insertar leads"
  on leads for insert
  to service_role
  with check (true);

create policy "n8n puede actualizar el propio flujo de estado"
  on leads for update
  to service_role
  using (true);

-- Los datos de siembra (los catalogos que el workflow lee) viven en seed.sql,
-- al lado de este archivo. Se cargan despues de este esquema.
