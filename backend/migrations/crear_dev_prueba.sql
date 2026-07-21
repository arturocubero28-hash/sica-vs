-- Usuario desarrollador de prueba (solo entorno local de desarrollo).
-- email: dev@villasdelsol.hn
-- clave: Demo123@  (debe cambiarla en el primer login, ya que se marca
-- debe_cambiar_password=true)
INSERT INTO usuarios (
    uuid_publico, nombre, apellido, email, password_hash,
    rol, activo, debe_cambiar_password, biometria_activa,
    created_at, updated_at
) VALUES (
    gen_random_uuid(), 'Arturo', 'Dev', 'dev@villasdelsol.hn',
    '$2b$12$VZUdyFeSw4CF5zFTjDQKHO6F6ec2eisRkvVjKEzOqC.ppYWeay2w6',
    'desarrollador', true, true, false,
    now(), now()
);
