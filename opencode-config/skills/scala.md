# Skill: Scala
# Loaded on-demand when working with .scala, .sc files, Akka, Play

## Case Classes & Pattern Matching

```scala
// Case classes — immutable data with auto-generated equals, hashCode, copy
case class User(name: String, age: Int, role: Role = Role.Member)

enum Role:
  case Admin, Member, Guest

// Pattern matching — exhaustive and expressive
def describe(user: User): String = user match
  case User(name, _, Role.Admin)       => s"Admin: $name"
  case User(name, age, _) if age >= 18 => s"Adult: $name"
  case User(name, _, _)                => s"Minor: $name"

// Sealed traits for ADTs
sealed trait Shape
case class Circle(radius: Double) extends Shape
case class Rect(w: Double, h: Double) extends Shape

def area(s: Shape): Double = s match
  case Circle(r)  => Math.PI * r * r
  case Rect(w, h) => w * h
```

## Option, Either, Try — Error Handling

```scala
// Option — presence or absence
def findUser(id: String): Option[User] =
  users.find(_.id == id)

val name = findUser("123").map(_.name).getOrElse("Unknown")

// Either — typed errors
def parseAge(s: String): Either[String, Int] =
  s.toIntOption.toRight(s"'$s' is not a valid age")

// Try — exception-safe computation
import scala.util.{Try, Success, Failure}

val result: Try[Int] = Try(riskyComputation())
result match
  case Success(value) => println(s"Got $value")
  case Failure(ex)    => println(s"Failed: ${ex.getMessage}")

// Chain with for-comprehension
for
  age    <- parseAge(input)
  user   <- createUser(name, age)
  token  <- generateToken(user)
yield token
// Returns Either[String, Token] — short-circuits on first Left
```

## For-Comprehensions

```scala
// For-comprehension works with any type that has map/flatMap/withFilter
// Option, Either, Future, List, etc.

// List comprehension
val pairs = for
  x <- 1 to 5
  y <- 1 to 5
  if x != y
yield (x, y)

// Future composition
import scala.concurrent.Future
import scala.concurrent.ExecutionContext.Implicits.global

def fetchDashboard(userId: String): Future[Dashboard] = for
  user    <- fetchUser(userId)
  posts   <- fetchPosts(user.id)
  friends <- fetchFriends(user.id)
yield Dashboard(user, posts, friends)
```

## Traits & Implicits / Givens (Scala 3)

```scala
// Trait — composable behavior
trait Serializable:
  def toJson: String

trait Loggable:
  def logName: String = getClass.getSimpleName

// Type class pattern (Scala 3 — givens & using)
trait JsonEncoder[A]:
  def encode(a: A): String

object JsonEncoder:
  given JsonEncoder[String] with
    def encode(s: String): String = s"\"$s\""

  given JsonEncoder[Int] with
    def encode(i: Int): String = i.toString

  given listEncoder[A](using enc: JsonEncoder[A]): JsonEncoder[List[A]] with
    def encode(list: List[A]): String =
      list.map(enc.encode).mkString("[", ",", "]")

// Extension methods (Scala 3)
extension [A](a: A)
  def toJson(using enc: JsonEncoder[A]): String = enc.encode(a)

// Usage
val json = List(1, 2, 3).toJson  // "[1,2,3]"
```

## Akka Actors (Classic & Typed)

```scala
import akka.actor.typed.{ActorRef, Behavior}
import akka.actor.typed.scaladsl.Behaviors

// Typed actor
object Counter:
  sealed trait Command
  case object Increment extends Command
  case class GetCount(replyTo: ActorRef[Int]) extends Command

  def apply(count: Int = 0): Behavior[Command] =
    Behaviors.receiveMessage:
      case Increment =>
        Counter(count + 1)
      case GetCount(replyTo) =>
        replyTo ! count
        Behaviors.same
```

## Cats / ZIO for Functional Effects

```scala
// ZIO — typed functional effects
import zio.*

def fetchUser(id: String): ZIO[UserRepo, AppError, User] =
  for
    repo <- ZIO.service[UserRepo]
    user <- repo.find(id).someOrFail(AppError.NotFound(id))
    _    <- ZIO.logInfo(s"Fetched user: ${user.name}")
  yield user

// Cats Effect — IO monad
import cats.effect.IO

def program: IO[Unit] = for
  _    <- IO.println("Enter name:")
  name <- IO.readLine
  _    <- IO.println(s"Hello, $name!")
yield ()
```

## Collections API

```scala
val numbers = List(1, 2, 3, 4, 5)

numbers.filter(_ > 2)              // List(3, 4, 5)
numbers.map(_ * 2)                 // List(2, 4, 6, 8, 10)
numbers.foldLeft(0)(_ + _)         // 15
numbers.groupBy(_ % 2 == 0)       // Map(false -> List(1,3,5), true -> List(2,4))
numbers.sliding(2).toList          // List(List(1,2), List(2,3), ...)
numbers.zip(List("a","b","c"))     // List((1,a), (2,b), (3,c))

// LazyList for infinite sequences
val fibs: LazyList[BigInt] =
  BigInt(0) #:: BigInt(1) #:: fibs.zip(fibs.tail).map(_ + _)
fibs.take(10).toList
```

## sbt Build

```scala
// build.sbt
ThisBuild / scalaVersion := "3.4.0"
ThisBuild / organization := "com.example"

lazy val root = (project in file("."))
  .settings(
    name := "myapp",
    libraryDependencies ++= Seq(
      "dev.zio"       %% "zio"        % "2.0.21",
      "dev.zio"       %% "zio-http"   % "3.0.0-RC4",
      "org.scalatest" %% "scalatest"  % "3.2.17" % Test,
      "org.scalameta" %% "munit"      % "1.0.0"  % Test,
    ),
    testFrameworks += new TestFramework("munit.Framework"),
  )
```

## Testing (ScalaTest & MUnit)

```scala
// MUnit
class UserSuite extends munit.FunSuite:
  test("parse valid age"):
    assertEquals(parseAge("25"), Right(25))

  test("parse invalid age"):
    assert(parseAge("abc").isLeft)

// ScalaTest
class UserSpec extends AnyFlatSpec with Matchers:
  "parseAge" should "return Right for valid input" in:
    parseAge("25") shouldBe Right(25)

  it should "return Left for invalid input" in:
    parseAge("abc") shouldBe a[Left[_, _]]
```

## Best Practices

- Prefer `val` over `var` — immutability by default.
- Use `case class` for data, `enum`/`sealed trait` for ADTs.
- Prefer for-comprehensions over nested `flatMap` for readability.
- Use `Option` instead of `null` — never use `null` in Scala.
- Prefer `Either[Error, A]` over throwing exceptions for expected failures.
- Use Scala 3 syntax (significant indentation, `given`/`using`, `enum`).
- Keep implicits/givens in companion objects for automatic resolution.
- Run `scalafmt` and `scalafix` in CI for consistent style.
