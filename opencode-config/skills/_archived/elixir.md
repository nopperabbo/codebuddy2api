# Skill: Elixir
# Loaded on-demand when working with .ex, .exs files, Phoenix, LiveView

## Pattern Matching & Pipe Operator

```elixir
# Pattern matching — the foundation of Elixir
{:ok, user} = Repo.get(User, id)
%{name: name, age: age} = user
[head | tail] = [1, 2, 3]

# Function clause matching
def greet(%{role: :admin, name: name}), do: "Welcome back, #{name}!"
def greet(%{name: name}), do: "Hello, #{name}"

# Pipe operator — chain transformations left to right
result =
  raw_input
  |> String.trim()
  |> String.downcase()
  |> String.split(",")
  |> Enum.map(&String.trim/1)
  |> Enum.reject(&(&1 == ""))
```

## GenServer & OTP

```elixir
defmodule MyApp.Counter do
  use GenServer

  # Client API
  def start_link(initial \\ 0),
    do: GenServer.start_link(__MODULE__, initial, name: __MODULE__)

  def increment, do: GenServer.cast(__MODULE__, :increment)
  def get_count, do: GenServer.call(__MODULE__, :get)

  # Server callbacks
  @impl true
  def init(initial), do: {:ok, initial}

  @impl true
  def handle_cast(:increment, count), do: {:noreply, count + 1}

  @impl true
  def handle_call(:get, _from, count), do: {:reply, count, count}
end
```

## Supervisor Trees

```elixir
defmodule MyApp.Application do
  use Application

  @impl true
  def start(_type, _args) do
    children = [
      MyApp.Repo,                                    # Ecto repo
      {Phoenix.PubSub, name: MyApp.PubSub},          # PubSub
      MyAppWeb.Endpoint,                              # Phoenix endpoint
      {MyApp.Counter, 0},                             # Custom GenServer
      {Task.Supervisor, name: MyApp.TaskSupervisor},  # Dynamic tasks
    ]

    opts = [strategy: :one_for_one, name: MyApp.Supervisor]
    Supervisor.start_link(children, opts)
  end
end

# Strategies:
# :one_for_one  — restart only the failed child
# :one_for_all  — restart all children if one fails
# :rest_for_one — restart failed child and those started after it
```

## Phoenix Controllers & Contexts

```elixir
# Context — business logic boundary
defmodule MyApp.Accounts do
  alias MyApp.Repo
  alias MyApp.Accounts.User

  def list_users, do: Repo.all(User)

  def get_user!(id), do: Repo.get!(User, id)

  def create_user(attrs) do
    %User{}
    |> User.changeset(attrs)
    |> Repo.insert()
  end
end

# Controller
defmodule MyAppWeb.UserController do
  use MyAppWeb, :controller

  alias MyApp.Accounts

  def index(conn, _params) do
    users = Accounts.list_users()
    render(conn, :index, users: users)
  end

  def create(conn, %{"user" => user_params}) do
    case Accounts.create_user(user_params) do
      {:ok, user} ->
        conn |> put_flash(:info, "Created!") |> redirect(to: ~p"/users/#{user}")
      {:error, changeset} ->
        render(conn, :new, changeset: changeset)
    end
  end
end
```

## Ecto Schemas, Changesets & Queries

```elixir
defmodule MyApp.Accounts.User do
  use Ecto.Schema
  import Ecto.Changeset

  schema "users" do
    field :name, :string
    field :email, :string
    field :role, Ecto.Enum, values: [:user, :admin], default: :user
    has_many :posts, MyApp.Blog.Post
    timestamps()
  end

  def changeset(user, attrs) do
    user
    |> cast(attrs, [:name, :email, :role])
    |> validate_required([:name, :email])
    |> validate_format(:email, ~r/@/)
    |> unique_constraint(:email)
  end
end

# Composable queries
import Ecto.Query

def active_admins do
  from(u in User,
    where: u.role == :admin and not is_nil(u.confirmed_at),
    order_by: [desc: u.inserted_at],
    preload: [:posts]
  )
  |> Repo.all()
end
```

## Phoenix LiveView

```elixir
defmodule MyAppWeb.CounterLive do
  use MyAppWeb, :live_view

  @impl true
  def mount(_params, _session, socket) do
    {:ok, assign(socket, count: 0)}
  end

  @impl true
  def handle_event("increment", _params, socket) do
    {:noreply, update(socket, :count, &(&1 + 1))}
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div>
      <h1>Count: <%= @count %></h1>
      <button phx-click="increment">+1</button>
    </div>
    """
  end
end
```

## Concurrency Patterns

```elixir
# Task — fire-and-forget or awaitable
task = Task.async(fn -> expensive_computation() end)
result = Task.await(task, 10_000)  # 10s timeout

# Task.Supervisor — supervised async work
Task.Supervisor.async_nolink(MyApp.TaskSupervisor, fn ->
  send_welcome_email(user)
end)

# Agent — simple state wrapper
{:ok, pid} = Agent.start_link(fn -> %{} end, name: :cache)
Agent.update(:cache, &Map.put(&1, key, value))
Agent.get(:cache, &Map.get(&1, key))
```

## Testing (ExUnit)

```elixir
defmodule MyApp.AccountsTest do
  use MyApp.DataCase, async: true

  alias MyApp.Accounts

  describe "create_user/1" do
    test "with valid attrs creates user" do
      assert {:ok, user} = Accounts.create_user(%{name: "Alice", email: "a@b.com"})
      assert user.name == "Alice"
    end

    test "with invalid email returns error changeset" do
      assert {:error, changeset} = Accounts.create_user(%{name: "Alice", email: "bad"})
      assert %{email: ["has invalid format"]} = errors_on(changeset)
    end
  end
end

# Mox for mocking
Mox.defmock(MyApp.HTTPClientMock, for: MyApp.HTTPClient)
expect(MyApp.HTTPClientMock, :get, fn _url -> {:ok, %{status: 200}} end)
```

## With Statement & Protocols

```elixir
# with — chain pattern matches, bail on first failure
with {:ok, user} <- Accounts.get_user(id),
     {:ok, token} <- Auth.generate_token(user),
     :ok <- Mailer.send_welcome(user) do
  {:ok, %{user: user, token: token}}
else
  {:error, :not_found} -> {:error, "User not found"}
  {:error, reason} -> {:error, reason}
end

# Protocols — polymorphism
defprotocol Renderable do
  def render(data)
end

defimpl Renderable, for: Map do
  def render(map), do: Jason.encode!(map)
end
```

## Best Practices

- Use contexts to organize business logic — don't call `Repo` from controllers.
- Prefer `with` over nested `case` for multi-step operations.
- Use `async: true` in tests for parallel execution.
- Let processes crash — supervisors handle recovery (let it crash philosophy).
- Use `@impl true` on all callback implementations for compile-time checks.
- Run `mix format` and `mix credo --strict` in CI.
- Use `mix release` for production deployments — no Mix/Hex in production.
