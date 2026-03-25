using System.Data.SqlClient;
using Microsoft.AspNetCore.Mvc;

[ApiController]
[Route("api/[controller]")]
public class AuthController : ControllerBase
{
    [HttpGet("user")]
    public IActionResult GetUser(string id)
    {
        string query = "SELECT * FROM users WHERE id = '" + id + "'";
        using var conn = new SqlConnection(connectionString);
        conn.Open();
        var cmd = new SqlCommand(query, conn);
        return Ok(cmd.ExecuteReader().ToString());
    }

    private string connectionString = "Server=localhost;Database=mydb;";
}
