-- Create football players table for AFM
CREATE TABLE IF NOT EXISTS public.football_players (
  id text PRIMARY KEY,
  name text NOT NULL,
  rating integer,
  ranking integer,
  price numeric,
  wage numeric,
  stars integer,
  stats jsonb,
  created_at timestamptz DEFAULT now()
);

-- Seed: top 10 sample players (use server-side run in Supabase SQL editor)
INSERT INTO public.football_players (id, name, rating, ranking, price, wage, stars, stats) VALUES
('p001','Top Andre',92,1,12000,700,5,'{"goals":12,"assists":8,"appearances":15}'),
('p002','M. Mbappé (sample)',91,2,11500,680,5,'{"goals":10,"assists":7,"appearances":14}'),
('p003','La Min (sample)',90,3,11000,650,5,'{"goals":9,"assists":10,"appearances":16}'),
('p004','Player Four',88,4,8000,500,4,'{"goals":7,"assists":6,"appearances":13}'),
('p005','Player Five',86,5,7000,450,4,'{"goals":6,"assists":5,"appearances":12}'),
('p006','Player Six',85,6,6800,430,4,'{"goals":5,"assists":7,"appearances":14}'),
('p007','Player Seven',83,7,5000,350,3,'{"goals":4,"assists":3,"appearances":11}'),
('p008','Player Eight',81,8,4800,320,3,'{"goals":3,"assists":4,"appearances":10}'),
('p009','Player Nine',79,9,3000,200,2,'{"goals":2,"assists":2,"appearances":9}'),
('p010','Player Ten',76,10,2500,180,2,'{"goals":1,"assists":1,"appearances":8}')
ON CONFLICT (id) DO NOTHING;
