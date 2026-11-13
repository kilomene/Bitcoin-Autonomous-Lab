// Bitcoin double-SHA-256 miner top level for the lab's RTL.
// Takes the midstate of an 80-byte block header (state after the
// first 64 bytes), the remaining header fields, a nonce range and
// a target, and scans nonces until one meets the target or the
// range is exhausted. Two sha256_core passes per nonce (inner from
// the midstate, outer from the standard initial state).
//
// This is the design that runs on an FPGA after synthesis and the
// same RTL that the ASIC flow synthesizes to gates.

module sha256d_miner (
    input  wire         clk,
    input  wire         rst,
    input  wire         start,
    input  wire [255:0] midstate,     // state words in digest order
    input  wire [95:0]  tail12,       // header bytes 64..75 verbatim:
                                      // merkle bytes 28..31, then the
                                      // time and bits fields as stored
    input  wire [255:0] target,       // integer target
    input  wire [31:0]  nonce_start,
    input  wire [31:0]  nonce_end,    // exclusive
    output reg          done,
    output reg          found,
    output reg  [31:0]  found_nonce,
    output reg  [255:0] found_hash,   // digest bytes, stream order
    output reg  [63:0]  hashes_done
);
    localparam [255:0] H0 = {
        32'h6a09e667, 32'hbb67ae85, 32'h3c6ef372, 32'ha54ff53a,
        32'h510e527f, 32'h9b05688c, 32'h1f83d9ab, 32'h5be0cd19};

    reg  [31:0]  nonce;
    reg          core_start;
    reg  [511:0] core_block;
    reg  [255:0] core_state_in;
    wire         core_done;
    wire [255:0] core_state_out;
    reg  [255:0] inner_digest;

    sha256_core core (
        .clk(clk), .rst(rst), .start(core_start), .block(core_block),
        .state_in(core_state_in), .done(core_done),
        .state_out(core_state_out));

    // The second compression block covers header bytes 64..79:
    // tail12 (bytes 64..75) followed by the nonce (bytes 76..79)
    // in stream order, then SHA-256 padding for a 640-bit message.
    wire [31:0] nonce_be = {nonce[7:0], nonce[15:8], nonce[23:16],
                            nonce[31:24]};
    wire [511:0] inner_block = {tail12, nonce_be, 8'h80, 312'b0, 64'd640};
    wire [511:0] outer_block = {inner_digest, 8'h80, 184'b0, 64'd256};

    // Digest as an integer: full byte reversal of the byte stream.
    wire [255:0] digest_int = {
        core_state_out[7:0],     core_state_out[15:8],
        core_state_out[23:16],   core_state_out[31:24],
        core_state_out[39:32],   core_state_out[47:40],
        core_state_out[55:48],   core_state_out[63:56],
        core_state_out[71:64],   core_state_out[79:72],
        core_state_out[87:80],   core_state_out[95:88],
        core_state_out[103:96],  core_state_out[111:104],
        core_state_out[119:112], core_state_out[127:120],
        core_state_out[135:128], core_state_out[143:136],
        core_state_out[151:144], core_state_out[159:152],
        core_state_out[167:160], core_state_out[175:168],
        core_state_out[183:176], core_state_out[191:184],
        core_state_out[199:192], core_state_out[207:200],
        core_state_out[215:208], core_state_out[223:216],
        core_state_out[231:224], core_state_out[239:232],
        core_state_out[247:240], core_state_out[255:248]};

    localparam IDLE = 0, INNER_GO = 1, INNER_WAIT = 2,
               OUTER_GO = 3, OUTER_WAIT = 4, NEXT = 5, FIN = 6;
    reg [2:0] state;

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; done <= 0; found <= 0; core_start <= 0;
            hashes_done <= 0;
        end else begin
            core_start <= 0;
            case (state)
                IDLE: begin
                    done <= 0; found <= 0; hashes_done <= 0;
                    nonce <= nonce_start;
                    if (start) state <= INNER_GO;
                end
                INNER_GO: begin
                    core_block <= inner_block;
                    core_state_in <= midstate;
                    core_start <= 1;
                    state <= INNER_WAIT;
                end
                INNER_WAIT: begin
                    if (core_done) begin
                        inner_digest <= core_state_out;
                        state <= OUTER_GO;
                    end
                end
                OUTER_GO: begin
                    core_block <= outer_block;
                    core_state_in <= H0;
                    core_start <= 1;
                    state <= OUTER_WAIT;
                end
                OUTER_WAIT: begin
                    if (core_done) begin
                        hashes_done <= hashes_done + 1;
                        if (digest_int <= target) begin
                            found <= 1;
                            found_nonce <= nonce;
                            found_hash <= core_state_out;
                            state <= FIN;
                        end else begin
                            state <= NEXT;
                        end
                    end
                end
                NEXT: begin
                    nonce <= nonce + 1;
                    if (nonce + 1 >= nonce_end) begin
                        state <= FIN;
                    end else begin
                        state <= INNER_GO;
                    end
                end
                FIN: begin
                    done <= 1;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
