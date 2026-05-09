# Skill: Ruby on Rails
# Loaded on-demand when working with Rails, ActiveRecord, ERB

## ActiveRecord — Associations, Scopes, Optimization
```ruby
class Post < ApplicationRecord
  belongs_to :author, class_name: 'User'
  has_many :comments, dependent: :destroy
  has_many :commenters, through: :comments, source: :user
  has_and_belongs_to_many :tags

  scope :published, -> { where('published_at <= ?', Time.current) }
  scope :by_category, ->(id) { where(category_id: id) if id.present? }
  scope :recent, -> { order(published_at: :desc) }
  scope :trending, -> { published.where('published_at > ?', 7.days.ago).order(views_count: :desc) }

  validates :title, presence: true, length: { maximum: 255 }
  validates :slug, uniqueness: true
  before_validation :generate_slug, on: :create

  private
  def generate_slug = self.slug = title&.parameterize
end

# N+1 prevention — ALWAYS eager load in controllers
posts = Post.includes(:author, :tags).published.recent.page(params[:page])
# ANTI-PATTERN: <% Post.all.each { |p| p.author.name } %> — query per post!

# Batch processing
Post.where('created_at < ?', 1.year.ago).find_each(batch_size: 1000, &:archive!)
```

## Controllers & Routing
```ruby
class Api::V1::PostsController < ApplicationController
  before_action :authenticate_user!, except: [:index, :show]
  before_action :set_post, only: [:show, :update, :destroy]

  def index
    posts = Post.includes(:author, :tags).published.by_category(params[:category_id]).recent.page(params[:page]).per(20)
    render json: posts, each_serializer: PostSerializer, meta: pagination_meta(posts)
  end

  def create
    post = current_user.posts.build(post_params)
    authorize post
    if post.save
      render json: post, serializer: PostSerializer, status: :created
    else
      render json: { errors: post.errors.full_messages }, status: :unprocessable_entity
    end
  end

  def destroy
    authorize @post
    @post.destroy
    head :no_content
  end

  private
  def set_post = @post = Post.find(params[:id])
  def post_params = params.require(:post).permit(:title, :body, :category_id, tag_ids: [])
end

# Routing — resources, nested, concerns
Rails.application.routes.draw do
  namespace :api, defaults: { format: :json } do
    namespace :v1 do
      resources :posts do
        resources :comments, only: [:index, :create, :destroy]
        member { post :publish }
      end
    end
  end
end
```

## Turbo, Hotwire & Stimulus (Rails 7+)
```erb
<%# Turbo Frame — partial page updates without full reload %>
<%= turbo_frame_tag "post_#{post.id}" do %>
  <div class="post"><h2><%= post.title %></h2></div>
<% end %>
```
```ruby
# Turbo Stream response in controller
respond_to do |format|
  format.turbo_stream { render turbo_stream: turbo_stream.prepend("posts", partial: "posts/post", locals: { post: @post }) }
  format.html { redirect_to posts_path }
end
```

## Jobs, ActionCable & Caching
```ruby
class NotifySubscribersJob < ApplicationJob
  queue_as :default
  retry_on Net::OpenTimeout, wait: :polynomially_longer, attempts: 5
  discard_on ActiveJob::DeserializationError
  def perform(post)
    post.author.subscribers.find_each { |s| NotificationMailer.new_post(s, post).deliver_later }
  end
end

# ActionCable — stream_from "chat_#{room_id}", handle messages via #speak
# Russian doll caching — touch: true auto-expires parent
<% cache @post do %>
  <% @post.comments.each { |c| cache(c) { render c } } %>
<% end %>
# belongs_to :post, touch: true  # in Comment model
```

## Testing — RSpec & FactoryBot
```ruby
RSpec.describe "Posts API", type: :request do
  let(:user) { create(:user) }
  let(:headers) { auth_headers(user) }

  it "creates a post" do
    expect {
      post "/api/v1/posts", params: { post: attributes_for(:post, category_id: create(:category).id) }, headers: headers, as: :json
    }.to change(Post, :count).by(1)
    expect(response).to have_http_status(:created)
  end
end

FactoryBot.define do
  factory :post do
    association :author, factory: :user
    title { Faker::Lorem.sentence }
    trait(:published) { published_at { Time.current } }
    trait(:with_comments) do
      transient { comments_count { 3 } }
      after(:create) { |post, ctx| create_list(:comment, ctx.comments_count, post: post) }
    end
  end
end
```

## Anti-Patterns Summary
| Anti-Pattern | Fix |
|---|---|
| N+1 queries | `includes`, `preload`; use `bullet` gem |
| Fat controllers | Service objects, form objects |
| Callbacks for business logic | Service objects; callbacks for data integrity only |
| String interpolation in SQL | Parameterized queries |
| No background jobs | ActiveJob + Sidekiq for anything > 100ms |
| Missing DB indexes | Index all FKs and search columns |
