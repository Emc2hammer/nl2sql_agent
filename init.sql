-- Sample data initialization for NL2SQL demo
-- This creates example tables: users, categories, products, orders

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(200) UNIQUE NOT NULL,
    age INTEGER,
    city VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    stock INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sample data
INSERT INTO users (name, email, age, city) VALUES
    ('张三', 'zhangsan@example.com', 28, '北京'),
    ('李四', 'lisi@example.com', 35, '上海'),
    ('王五', 'wangwu@example.com', 42, '深圳'),
    ('赵六', 'zhaoliu@example.com', 31, '广州'),
    ('孙七', 'sunqi@example.com', 25, '杭州');

INSERT INTO categories (name, description) VALUES
    ('电子产品', '手机、电脑、平板等电子设备'),
    ('服装', '衣服、鞋子、配饰等'),
    ('食品', '零食、饮料、生鲜等'),
    ('家居', '家具、日用品等');

INSERT INTO products (name, price, category_id, stock) VALUES
    ('iPhone 15', 6999.00, 1, 50),
    ('MacBook Pro', 14999.00, 1, 30),
    ('运动鞋', 599.00, 2, 200),
    ('羽绒服', 899.00, 2, 100),
    ('有机绿茶', 129.00, 3, 500),
    ('进口巧克力', 89.00, 3, 300),
    ('简约书桌', 1299.00, 4, 40),
    ('LED台灯', 199.00, 4, 150);

INSERT INTO orders (user_id, product_id, quantity, amount, status, created_at) VALUES
    (1, 1, 1, 6999.00, 'completed', '2026-05-01 10:30:00'),
    (1, 5, 2, 258.00, 'completed', '2026-05-02 14:00:00'),
    (2, 2, 1, 14999.00, 'completed', '2026-05-03 09:15:00'),
    (2, 8, 3, 597.00, 'pending', '2026-05-06 16:45:00'),
    (3, 3, 2, 1198.00, 'completed', '2026-05-04 11:20:00'),
    (3, 6, 5, 445.00, 'shipped', '2026-05-05 08:30:00'),
    (4, 4, 1, 899.00, 'completed', '2026-05-03 15:00:00'),
    (4, 7, 1, 1299.00, 'shipped', '2026-05-06 10:00:00'),
    (5, 3, 1, 599.00, 'pending', '2026-05-07 09:00:00'),
    (5, 5, 3, 387.00, 'completed', '2026-05-02 12:30:00');
